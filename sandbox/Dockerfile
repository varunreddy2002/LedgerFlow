FROM python:3.11-slim

RUN pip install --no-cache-dir matplotlib pandas numpy && \
    useradd -m sandbox

USER sandbox
WORKDIR /home/sandbox

CMD ["sleep", "infinity"]
