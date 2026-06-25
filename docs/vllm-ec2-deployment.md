# vLLM EC2 Deployment — H2OVL Mississippi 800M

## EC2 Instance Setup

- **AMI:** Deep Learning Base AMI with Single CUDA (Ubuntu 24.04)
- **Instance type:** `g4dn.xlarge` (1x Tesla T4, 16GB VRAM)
- **Storage:** 50GB gp3 (root) — the AMI includes a 115GB NVMe at `/opt/dlami/nvme`
- **Security group:** inbound TCP `22` (SSH) + `8000` (vLLM API)

---

## Configure Docker Storage

The vLLM image is ~20GB. Move Docker and containerd storage to the NVMe drive.

**`/etc/docker/daemon.json`**
```json
{
    "data-root": "/opt/dlami/nvme/docker",
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    }
}
```

**`/etc/containerd/config.toml`** — update the root line:
```toml
root = "/opt/dlami/nvme/containerd"
```

Restart both services:
```bash
sudo systemctl restart containerd
sudo systemctl restart docker
```

---

## Verify GPU Access from Docker

```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

Should show the Tesla T4 GPU.

---

## Run the vLLM Server

```bash
docker run --gpus all \
  -p 8000:8000 \
  --ipc=host \
  vllm/vllm-openai:v0.6.6 \
  --model h2oai/h2ovl-mississippi-800m \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.75 \
  --dtype half \
  --trust-remote-code \
  --host 0.0.0.0 \
  --port 8000
```

> **Why v0.6.6?** Latest vLLM ships with transformers 5.x which breaks the h2ovl model's custom config code. v0.6.6 ships with transformers 4.x which is compatible.
> **Why `--dtype half`?** T4 GPU (compute capability 7.5) does not support bfloat16. float16 (`half`) is required.

---

## Update .env

```env
VLLM_BASE_URL=http://<ec2-public-ip>:8000
VLLM_API_KEY=any-string
```

---

## To Run in Background

```bash
nohup docker run --gpus all \
  -p 8000:8000 \
  --ipc=host \
  vllm/vllm-openai:v0.6.6 \
  --model h2oai/h2ovl-mississippi-800m \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.75 \
  --dtype half \
  --trust-remote-code \
  --host 0.0.0.0 \
  --port 8000 > ~/vllm.log 2>&1 &
```

## Verify Server is Up

```bash
curl http://localhost:8000/v1/models
```
