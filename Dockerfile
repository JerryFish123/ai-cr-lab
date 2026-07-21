# 使用官方 Python 镜像（构建时建议配合国内 registry mirror）
FROM python:3.10-slim

WORKDIR /app

# Debian / PyPI 使用国内镜像，加快 ECS（国内）构建
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources; \
      sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
      sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list; \
      sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list; \
    fi

RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    git \
    ca-certificates \
    ripgrep \
    tree \
    file \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# spark-ai-python 非运行必需，安装失败时跳过以免卡住部署
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
      -r requirements.txt \
    || pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
      anthropic==0.39.0 Flask==3.0.3 APScheduler==3.10.4 "httpx[socks]" Jinja2==3.1.4 \
      lizard==1.17.20 matplotlib==3.10.1 ollama==0.4.7 openai==1.59.3 pandas==2.2.3 \
      pathspec==0.12.1 PyMySQL==1.1.1 python-gitlab==5.6.0 requests==2.32.3 \
      streamlit==1.42.2 streamlit-cookies-manager==0.2.0 tiktoken==0.9.0 \
      zhipuai==2.1.5.20230904 python-dotenv blinker PyYAML

RUN mkdir -p log data conf
COPY biz ./biz
COPY fonts ./fonts
COPY api.py ./api.py
COPY ui.py ./ui.py
COPY conf/prompt_templates.yml ./conf/prompt_templates.yml
COPY conf/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 5001 5002

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
