from blinker import Signal

from biz.entity.review_entity import MergeRequestReviewEntity, PushReviewEntity
from biz.service.review_service import ReviewService
from biz.utils.im import notifier

# 定义全局事件管理器（事件信号）
event_manager = {
    "merge_request_reviewed": Signal(),
    "push_reviewed": Signal(),
}


# 定义事件处理函数
def on_merge_request_reviewed(mr_review_entity: MergeRequestReviewEntity):
    # PR/MR 钉钉摘要已由 worker 在审查结束时单独发送，这里只落库，避免刷整份长报告。
    ReviewService().insert_mr_review_log(mr_review_entity)


def on_push_reviewed(entity: PushReviewEntity):
    # 无关注文件变更时不刷钉钉，减少噪音
    if entity.review_result == "关注的文件没有修改":
        ReviewService().insert_push_review_log(entity)
        return

    # 发送IM消息通知
    im_msg = f"### 🚀 {entity.project_name}: Push\n\n"
    im_msg += "#### 提交记录:\n"

    for commit in entity.commits:
        message = commit.get('message', '').strip()
        author = commit.get('author', 'Unknown Author')
        timestamp = commit.get('timestamp', '')
        url = commit.get('url', '#')
        im_msg += (
            f"- **提交信息**: {message}\n"
            f"- **提交者**: {author}\n"
            f"- **时间**: {timestamp}\n"
            f"- [查看提交详情]({url})\n\n"
        )

    if entity.review_result:
        im_msg += f"#### AI Review 结果: \n {entity.review_result}\n\n"
    notifier.send_notification(content=im_msg, msg_type='markdown',title=f"{entity.project_name} Push Event",
                               project_name=entity.project_name, url_slug=entity.url_slug,
                               webhook_data=entity.webhook_data)

    # 记录到数据库
    ReviewService().insert_push_review_log(entity)


# 连接事件处理函数到事件信号
event_manager["merge_request_reviewed"].connect(on_merge_request_reviewed)
event_manager["push_reviewed"].connect(on_push_reviewed)
