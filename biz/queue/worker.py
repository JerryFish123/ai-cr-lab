import os
import traceback
from datetime import datetime

from biz.entity.review_entity import MergeRequestReviewEntity, PushReviewEntity
from biz.event.event_manager import event_manager
from biz.platforms.gitlab.webhook_handler import filter_changes, MergeRequestHandler, PushHandler
from biz.platforms.github.webhook_handler import filter_changes as filter_github_changes, PullRequestHandler as GithubPullRequestHandler, PushHandler as GithubPushHandler
from biz.platforms.gitea.webhook_handler import filter_changes as filter_gitea_changes, PullRequestHandler as GiteaPullRequestHandler, \
    PushHandler as GiteaPushHandler
from biz.service.review_service import ReviewService
from biz.agent.agentic_reviewer import AgenticReviewError
from biz.prd.description import extract_description_body, parse_prd_intent
from biz.review.triple_review import run_triple_review
from biz.utils.code_reviewer import CodeReviewer
from biz.utils.im import notifier
from biz.utils.im.review_notify import (
    notify_review_finished,
    notify_review_started,
    pr_meta_from_webhook,
)
from biz.utils.log import logger
from biz.utils.review_report_format import normalize_triple_report, trim_quality_report_for_publish


def _prd_intent_for_webhook(webhook_data: dict):
    return parse_prd_intent(extract_description_body(webhook_data))


def _notify_review_started_for_pr(
    *,
    webhook_data: dict,
    url_slug: str,
    file_count: int,
) -> bool:
    """Send DingTalk start notice. Returns whether PRD analysis will run."""
    intent = _prd_intent_for_webhook(webhook_data)
    has_prd = intent.should_run_requirement_review
    meta = pr_meta_from_webhook(webhook_data)
    notify_review_started(
        project_name=meta["project_name"],
        author=meta["author"],
        source_branch=meta["source_branch"],
        target_branch=meta["target_branch"],
        url=meta["url"],
        has_prd=has_prd,
        file_count=file_count,
        url_slug=url_slug,
        webhook_data=webhook_data,
    )
    return has_prd


def _notify_review_finished_for_pr(
    *,
    webhook_data: dict,
    url_slug: str,
    review_report: str,
    has_prd: bool,
) -> None:
    meta = pr_meta_from_webhook(webhook_data)
    notify_review_finished(
        project_name=meta["project_name"],
        author=meta["author"],
        url=meta["url"],
        quality_report=review_report,
        requirement_report=None,
        has_prd=has_prd,
        url_slug=url_slug,
        webhook_data=webhook_data,
    )


def _resolve_repo_for_event(webhook_data: dict, gitlab_url: str = "") -> tuple[str | None, str | None, str | None]:
    """Infer (repo_url, repo_key, ref) for agentic mode from a webhook payload.

    Returns (None, None, None) if it can't be determined (caller should degrade).
    """
    # GitLab MR
    if webhook_data.get("object_kind") == "merge_request":
        repo = webhook_data.get("project", {})
        path = repo.get("path_with_namespace") or repo.get("name")
        url = repo.get("git_http_url") or repo.get("url") or (gitlab_url.rstrip("/") + "/" + path if path and gitlab_url else None)
        attrs = webhook_data.get("object_attributes", {})
        ref = attrs.get("source_branch") or attrs.get("ref")
        sha = (attrs.get("last_commit") or {}).get("id")
        if path and url and (ref or sha):
            return url, path, sha or ref
        return None, None, None
    # GitLab push
    if webhook_data.get("object_kind") == "push":
        repo = webhook_data.get("project", {})
        path = repo.get("path_with_namespace") or repo.get("name")
        url = repo.get("git_http_url") or repo.get("url") or (gitlab_url.rstrip("/") + "/" + path if path and gitlab_url else None)
        ref = webhook_data.get("after") or webhook_data.get("ref")
        if path and url and ref:
            return url, path, ref
        return None, None, None
    # GitHub / Gitea PR
    if "repository" in webhook_data and "pull_request" in webhook_data:
        repo = webhook_data["repository"]
        url = repo.get("clone_url") or repo.get("html_url")
        path = repo.get("full_name")
        pr = webhook_data["pull_request"]
        ref = pr.get("head", {}).get("sha") or pr.get("head", {}).get("ref")
        if path and url and ref:
            return url, path, ref
        return None, None, None
    if "repository" in webhook_data and "ref" in webhook_data:
        repo = webhook_data["repository"]
        url = repo.get("clone_url") or repo.get("html_url")
        path = repo.get("full_name")
        ref = webhook_data.get("after") or webhook_data.get("head_commit", {}).get("id")
        if path and url and ref:
            return url, path, ref
        return None, None, None
    return None, None, None


def _run_code_review(
    *,
    changes: list,
    commits_text: str,
    webhook_data: dict,
    access_token: str,
    platform_url: str,
) -> str:
    """Single three-section review report (agentic triple, or diff_only fallback)."""
    strategy = os.getenv("REVIEW_STRATEGY", "diff_only")
    repo_url, repo_key, ref = _resolve_repo_for_event(webhook_data, platform_url)

    if strategy == "agentic":
        return run_triple_review(
            changes=changes,
            commits_text=commits_text,
            webhook_data=webhook_data,
            access_token=access_token,
            platform_url=platform_url,
            repo_url=repo_url,
            repo_key=repo_key,
            ref=ref,
        )

    # diff_only: still emit triple shape; no PRD probe.
    report = CodeReviewer().review_and_strip_code(str(changes), commits_text)
    report = trim_quality_report_for_publish(report)
    intent = parse_prd_intent(extract_description_body(webhook_data))
    if intent.should_run_requirement_review:
        return normalize_triple_report(
            (
                "### 1. PRD 覆盖情况\n\n"
                "- （当前为 diff_only，未做 PRD 探查；请设置 REVIEW_STRATEGY=agentic）\n\n"
                "### 2. 非 PRD 范围的潜在波及\n\n"
                "- （同上）\n\n"
                f"### 3. 安全与性能风险\n\n{report or '- 未发现明显安全或性能风险'}"
            ),
            has_prd=True,
        )
    return normalize_triple_report("", has_prd=False, risk_section=report)


def handle_push_event(webhook_data: dict, gitlab_token: str, gitlab_url: str, gitlab_url_slug: str):
    push_review_enabled = os.environ.get('PUSH_REVIEW_ENABLED', '0') == '1'
    try:
        handler = PushHandler(webhook_data, gitlab_token, gitlab_url)
        logger.info('Push Hook event received')
        commits = handler.get_push_commits()
        if not commits:
            logger.error('Failed to get commits')
            return

        review_result = None
        score = 0
        additions = 0
        deletions = 0
        if push_review_enabled:
            changes = handler.get_push_changes()
            logger.info('changes: %s', changes)
            changes = filter_changes(changes)
            if not changes:
                logger.info('未检测到PUSH代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            review_result = "关注的文件没有修改"

            if len(changes) > 0:
                commits_text = ';'.join(commit.get('message', '').strip() for commit in commits)
                review_result = _run_code_review(
                    changes=changes,
                    commits_text=commits_text,
                    webhook_data=webhook_data,
                    access_token=gitlab_token,
                    platform_url=gitlab_url,
                )
                for item in changes:
                    additions += item['additions']
                    deletions += item['deletions']
            handler.add_push_notes(f'Auto Review Result: \n{review_result}')

        event_manager['push_reviewed'].send(PushReviewEntity(
            project_name=webhook_data['project']['name'],
            author=webhook_data['user_username'],
            branch=webhook_data.get('ref', '').replace('refs/heads/', ''),
            updated_at=int(datetime.now().timestamp()),
            commits=commits,
            score=score,
            review_result=review_result,
            url_slug=gitlab_url_slug,
            webhook_data=webhook_data,
            additions=additions,
            deletions=deletions,
        ))

    except AgenticReviewError as e:
        logger.error('agentic review failed (already notified): %s', e)
    except Exception as e:
        error_message = f'服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        notifier.send_notification(content=error_message)
        logger.error('出现未知错误: %s', error_message)


def handle_merge_request_event(webhook_data: dict, gitlab_token: str, gitlab_url: str, gitlab_url_slug: str):
    '''
    处理Merge Request Hook事件
    '''
    merge_review_only_protected_branches = os.environ.get('MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED', '0') == '1'
    try:
        handler = MergeRequestHandler(webhook_data, gitlab_token, gitlab_url)
        logger.info('Merge Request Hook event received')

        object_attributes = webhook_data.get('object_attributes', {})
        is_draft = object_attributes.get('draft') or object_attributes.get('work_in_progress')
        if is_draft:
            msg = f"[通知] MR为草稿（draft），未触发AI审查。\n项目: {webhook_data['project']['name']}\n作者: {webhook_data['user']['username']}\n源分支: {object_attributes.get('source_branch')}\n目标分支: {object_attributes.get('target_branch')}\n链接: {object_attributes.get('url')}"
            notifier.send_notification(content=msg)
            logger.info("MR为draft，仅发送通知，不触发AI review。")
            return

        if merge_review_only_protected_branches and not handler.target_branch_protected():
            logger.info("Merge Request target branch not match protected branches, ignored.")
            return

        if handler.action not in ['open', 'update']:
            logger.info(f"Merge Request Hook event, action={handler.action}, ignored.")
            return

        last_commit_id = object_attributes.get('last_commit', {}).get('id', '')
        if last_commit_id:
            project_name = webhook_data['project']['name']
            source_branch = object_attributes.get('source_branch', '')
            target_branch = object_attributes.get('target_branch', '')

            if ReviewService.check_mr_last_commit_id_exists(project_name, source_branch, target_branch, last_commit_id):
                logger.info(f"Merge Request with last_commit_id {last_commit_id} already exists, skipping review for {project_name}.")
                return

        changes = handler.get_merge_request_changes()
        logger.info('changes: %s', changes)
        changes = filter_changes(changes)
        if not changes:
            logger.info('未检测到有关代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            return
        additions = 0
        deletions = 0
        for item in changes:
            additions += item.get('additions', 0)
            deletions += item.get('deletions', 0)

        commits = handler.get_merge_request_commits()
        if not commits:
            logger.error('Failed to get commits')
            return

        has_prd = _notify_review_started_for_pr(
            webhook_data=webhook_data,
            url_slug=gitlab_url_slug,
            file_count=len(changes),
        )

        commits_text = ';'.join(commit.get('message', '').strip() for commit in commits)
        review_result = _run_code_review(
            changes=changes,
            commits_text=commits_text,
            webhook_data=webhook_data,
            access_token=gitlab_token,
            platform_url=gitlab_url,
        )

        handler.add_merge_request_notes(f'Auto Review Result: \n{review_result}')

        _notify_review_finished_for_pr(
            webhook_data=webhook_data,
            url_slug=gitlab_url_slug,
            review_report=review_result,
            has_prd=has_prd,
        )

        event_manager['merge_request_reviewed'].send(
            MergeRequestReviewEntity(
                project_name=webhook_data['project']['name'],
                author=webhook_data['user']['username'],
                source_branch=webhook_data['object_attributes']['source_branch'],
                target_branch=webhook_data['object_attributes']['target_branch'],
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=0,
                url=webhook_data['object_attributes']['url'],
                review_result=review_result,
                url_slug=gitlab_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
                last_commit_id=last_commit_id,
            )
        )

    except AgenticReviewError as e:
        logger.error('agentic review failed (already notified): %s', e)
    except Exception as e:
        error_message = f'AI Code Review 服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        notifier.send_notification(content=error_message)
        logger.error('出现未知错误: %s', error_message)


def handle_github_push_event(webhook_data: dict, github_token: str, github_url: str, github_url_slug: str):
    push_review_enabled = os.environ.get('PUSH_REVIEW_ENABLED', '0') == '1'
    try:
        handler = GithubPushHandler(webhook_data, github_token, github_url)
        logger.info('GitHub Push event received')
        commits = handler.get_push_commits()
        if not commits:
            logger.error('Failed to get commits')
            return

        review_result = None
        score = 0
        additions = 0
        deletions = 0
        if push_review_enabled:
            changes = handler.get_push_changes()
            logger.info('changes: %s', changes)
            changes = filter_github_changes(changes)
            if not changes:
                logger.info('未检测到PUSH代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            review_result = "关注的文件没有修改"

            if len(changes) > 0:
                commits_text = ';'.join(commit.get('message', '').strip() for commit in commits)
                review_result = _run_code_review(
                    changes=changes,
                    commits_text=commits_text,
                    webhook_data=webhook_data,
                    access_token=github_token,
                    platform_url=github_url,
                )
                for item in changes:
                    additions += item.get('additions', 0)
                    deletions += item.get('deletions', 0)
            handler.add_push_notes(f'Auto Review Result: \n{review_result}')

        event_manager['push_reviewed'].send(PushReviewEntity(
            project_name=webhook_data['repository']['name'],
            author=webhook_data['sender']['login'],
            branch=webhook_data['ref'].replace('refs/heads/', ''),
            updated_at=int(datetime.now().timestamp()),
            commits=commits,
            score=score,
            review_result=review_result,
            url_slug=github_url_slug,
            webhook_data=webhook_data,
            additions=additions,
            deletions=deletions,
        ))

    except AgenticReviewError as e:
        logger.error('agentic review failed (already notified): %s', e)
    except Exception as e:
        error_message = f'服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        notifier.send_notification(content=error_message)
        logger.error('出现未知错误: %s', error_message)


def handle_github_pull_request_event(webhook_data: dict, github_token: str, github_url: str, github_url_slug: str):
    '''
    处理GitHub Pull Request 事件
    '''
    merge_review_only_protected_branches = os.environ.get('MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED', '0') == '1'
    try:
        handler = GithubPullRequestHandler(webhook_data, github_token, github_url)
        logger.info('GitHub Pull Request event received')
        if merge_review_only_protected_branches and not handler.target_branch_protected():
            logger.info("Merge Request target branch not match protected branches, ignored.")
            return

        if handler.action not in ['opened', 'synchronize']:
            logger.info(f"Pull Request Hook event, action={handler.action}, ignored.")
            return

        github_last_commit_id = webhook_data['pull_request']['head']['sha']
        if github_last_commit_id:
            project_name = webhook_data['repository']['name']
            source_branch = webhook_data['pull_request']['head']['ref']
            target_branch = webhook_data['pull_request']['base']['ref']

            if ReviewService.check_mr_last_commit_id_exists(project_name, source_branch, target_branch, github_last_commit_id):
                logger.info(f"Pull Request with last_commit_id {github_last_commit_id} already exists, skipping review for {project_name}.")
                return

        changes = handler.get_pull_request_changes()
        logger.info('changes: %s', changes)
        changes = filter_github_changes(changes)
        if not changes:
            logger.info('未检测到有关代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            return
        additions = 0
        deletions = 0
        for item in changes:
            additions += item.get('additions', 0)
            deletions += item.get('deletions', 0)

        commits = handler.get_pull_request_commits()
        if not commits:
            logger.error('Failed to get commits')
            return

        has_prd = _notify_review_started_for_pr(
            webhook_data=webhook_data,
            url_slug=github_url_slug,
            file_count=len(changes),
        )

        commits_text = ';'.join(commit.get('message', '').strip() for commit in commits)
        review_result = _run_code_review(
            changes=changes,
            commits_text=commits_text,
            webhook_data=webhook_data,
            access_token=github_token,
            platform_url=github_url,
        )

        handler.add_pull_request_notes(f'Auto Review Result: \n{review_result}')

        _notify_review_finished_for_pr(
            webhook_data=webhook_data,
            url_slug=github_url_slug,
            review_report=review_result,
            has_prd=has_prd,
        )

        event_manager['merge_request_reviewed'].send(
            MergeRequestReviewEntity(
                project_name=webhook_data['repository']['name'],
                author=webhook_data['pull_request']['user']['login'],
                source_branch=webhook_data['pull_request']['head']['ref'],
                target_branch=webhook_data['pull_request']['base']['ref'],
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=0,
                url=webhook_data['pull_request']['html_url'],
                review_result=review_result,
                url_slug=github_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
                last_commit_id=github_last_commit_id,
            ))

    except AgenticReviewError as e:
        logger.error('agentic review failed (already notified): %s', e)
    except Exception as e:
        error_message = f'服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        notifier.send_notification(content=error_message)
        logger.error('出现未知错误: %s', error_message)


def handle_gitea_push_event(webhook_data: dict, gitea_token: str, gitea_url: str, gitea_url_slug: str):
    push_review_enabled = os.environ.get('PUSH_REVIEW_ENABLED', '0') == '1'
    try:
        handler = GiteaPushHandler(webhook_data, gitea_token, gitea_url)
        logger.info('Gitea Push event received')
        commits = handler.get_push_commits()
        if not commits:
            logger.error('Failed to get commits')
            return

        review_result = None
        score = 0
        additions = 0
        deletions = 0
        if push_review_enabled:
            changes = handler.get_push_changes()
            logger.info('changes: %s', changes)
            changes = filter_gitea_changes(changes)
            if not changes:
                logger.info('未检测到PUSH代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            review_result = "关注的文件没有修改"

            if len(changes) > 0:
                commits_text = ';'.join(commit.get('message', '').strip() for commit in commits)
                review_result = _run_code_review(
                    changes=changes,
                    commits_text=commits_text,
                    webhook_data=webhook_data,
                    access_token=gitea_token,
                    platform_url=gitea_url,
                )
                for item in changes:
                    additions += item.get('additions', 0)
                    deletions += item.get('deletions', 0)
            handler.add_push_notes(f'Auto Review Result: \n{review_result}')

        repository = webhook_data.get('repository', {})
        sender = webhook_data.get('sender', {}) or webhook_data.get('pusher', {}) or {}

        event_manager['push_reviewed'].send(PushReviewEntity(
            project_name=repository.get('name'),
            author=sender.get('login') or sender.get('username'),
            branch=handler.branch_name,
            updated_at=int(datetime.now().timestamp()),
            commits=commits,
            score=score,
            review_result=review_result,
            url_slug=gitea_url_slug,
            webhook_data=webhook_data,
            additions=additions,
            deletions=deletions,
        ))

    except AgenticReviewError as e:
        logger.error('agentic review failed (already notified): %s', e)
    except Exception as e:
        error_message = f'服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        notifier.send_notification(content=error_message)
        logger.error('出现未知错误: %s', error_message)


def handle_gitea_pull_request_event(webhook_data: dict, gitea_token: str, gitea_url: str, gitea_url_slug: str):
    merge_review_only_protected_branches = os.environ.get('MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED', '0') == '1'
    try:
        handler = GiteaPullRequestHandler(webhook_data, gitea_token, gitea_url)
        logger.info('Gitea Pull Request event received')

        pull_request = webhook_data.get('pull_request', {})

        if merge_review_only_protected_branches and not handler.target_branch_protected():
            logger.info("Pull Request target branch not match protected branches, ignored.")
            return

        if handler.action not in ['opened', 'open', 'reopened', 'synchronize', 'synchronized']:
            logger.info(f"Pull Request Hook event, action={handler.action}, ignored.")
            return

        head_info = pull_request.get('head') or {}
        base_info = pull_request.get('base') or {}

        last_commit_id = head_info.get('sha') or pull_request.get('merge_commit_sha') or pull_request.get('last_commit_id')
        if last_commit_id:
            project_name = webhook_data.get('repository', {}).get('name')
            source_branch = head_info.get('ref') or pull_request.get('head_branch', '')
            target_branch = base_info.get('ref') or pull_request.get('base_branch', '')

            if ReviewService.check_mr_last_commit_id_exists(project_name, source_branch, target_branch, last_commit_id):
                logger.info(f"Pull Request with last_commit_id {last_commit_id} already exists, skipping review for {project_name}.")
                return

        changes = handler.get_pull_request_changes()
        logger.info('changes: %s', changes)
        changes = filter_gitea_changes(changes)
        if not changes:
            logger.info('未检测到有关代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            return

        additions = 0
        deletions = 0
        for item in changes:
            additions += item.get('additions', 0)
            deletions += item.get('deletions', 0)

        commits = handler.get_pull_request_commits()
        if not commits:
            logger.error('Failed to get commits for Gitea pull request')
            return

        commits_text = ';'.join(commit.get('message', '').strip() for commit in commits)

        has_prd = _notify_review_started_for_pr(
            webhook_data=webhook_data,
            url_slug=gitea_url_slug,
            file_count=len(changes),
        )

        review_result = _run_code_review(
            changes=changes,
            commits_text=commits_text,
            webhook_data=webhook_data,
            access_token=gitea_token,
            platform_url=gitea_url,
        )

        handler.add_pull_request_notes(f'Auto Review Result: \n{review_result}')

        _notify_review_finished_for_pr(
            webhook_data=webhook_data,
            url_slug=gitea_url_slug,
            review_report=review_result,
            has_prd=has_prd,
        )

        repository = webhook_data.get('repository', {})
        author_info = pull_request.get('user', {}) or webhook_data.get('sender', {}) or {}

        event_manager['merge_request_reviewed'].send(
            MergeRequestReviewEntity(
                project_name=repository.get('name'),
                author=author_info.get('login') or author_info.get('username'),
                source_branch=head_info.get('ref') or pull_request.get('head_branch', ''),
                target_branch=base_info.get('ref') or pull_request.get('base_branch', ''),
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=0,
                url=pull_request.get('html_url') or pull_request.get('url'),
                review_result=review_result,
                url_slug=gitea_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
                last_commit_id=last_commit_id,
            ))

    except AgenticReviewError as e:
        logger.error('agentic review failed (already notified): %s', e)
    except Exception as e:
        error_message = f'AI Code Review 服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        notifier.send_notification(content=error_message)
        logger.error('出现未知错误: %s', error_message)
