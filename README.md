<p align="center">
<img src="https://raw.githubusercontent.com/vlmOCR/Kalorda/refs/heads/main/frontend/public/logo.png" alt="Kalorda" align="center" style="margin: 20px 20px -20px 0;">
</p>
<h1 align="center" style="font-size: 60px;"><b>Kalorda</b></h1>
<p align="center" style="font-size: 25px;"><b>An integrated fine-tuning platform for lightweight vlmOCR models</b></p>
<p align="center">
<a href="https://github.com/modelscope/ms-swift" target="_blank"><img src="https://img.shields.io/badge/modelscope-ms--swift-red"></a>
<a href="https://github.com/vllm-project/vllm" target="_blank"><img src="https://img.shields.io/badge/vLLM-blue"></a>
<a href="https://vuejs.org/"><img src="https://img.shields.io/badge/Vue3+Vite-red"></a> 
<a href="https://github.com/vlmOCR/Kalorda"><img src="https://img.shields.io/badge/github-repo-blue?logo=github"></a>
<a href="https://pypi.org/project/kalorda"><img src="https://img.shields.io/badge/pypi-v0.1.6-orange"></a>
<a href="https://kalorda.vlmocr.com"><img src="https://img.shields.io/badge/Website-online-yellow"></a> 
<br/>
<a href="README.md">English</a>&nbsp;&nbsp;<a href="README_CN.md">中文</a>
</p>

🔥 News: Kalorda now supports fine-tuning for FireRed-OCR model/vllm v0.16.0/ms-swift v4.0.0

🔥 News: Kalorda now supports fine-tuning for Deepseek-OCR-2, and specifically supports higher vLLM versions (v0.13/0.14/0.15) for running inference with Deepseek-OCR-2 (first release online).

<img src="frontend/public/screenshot.png" width="100%" title="screenshot"/>

## Overview
Kalorda is a lightweight VLM OCR fine-tuning platform. The frontend is built with TypeScript + Vue3 + Vite, and the backend is built with Python + FastAPI + ms-swift + vLLM. It provides a one-stop solution for data relabeling, fine-tuning, and evaluation for mainstream lightweight VLM OCR models.

VLM OCR models are evolving rapidly. Different models have their own strengths and limitations, so real-world applications often need secondary fine-tuning to improve recognition performance in specific business scenarios. Although there are many open-source components available for data labeling, fine-tuning, and inference, there is still a lack of an integrated tool that links the entire workflow together. This makes fine-tuning work (even if it is just tool orchestration) inconvenient and challenging for non-experts. Kalorda wraps mainstream tools like ms-swift + vLLM and deeply integrates mainstream OCR models, providing an intuitive web UI that lowers the barrier to VLM OCR fine-tuning and makes operations simpler and more convenient.

Currently supported VLM OCR models:

| Model Name | Model Size | Release Date | Publisher |
| ----------- | ----------- | ----------- | ----------- |
| GOT-OCR2.0 | 0.6B     | May 2025 | StepFun |
| dotsOCR    | 3B       | Jul 2025 | Xiaohongshu |
| Dolphin_v2 | 3B       | Jan 2025 | ByteDance |
| Deepseek_OCR | 3B     | Jan 2025 | DeepSeek |
| PaddleOCR_VL | 0.9B   | Jan 2025 | Baidu |
| HunyuanOCR   | 1B     | Feb 2025 | Tencent |
| Deepseek_OCR2 | 3B     | Jan 2026 | DeepSeek |
| FireRed_OCR    | 2B       | Mar 2026 | Xiaohongshu |

More models will be integrated. PRs and issues are welcome.

## Installation

### Quick Install
Kalorda packages are published on [PyPI](https://pypi.org/). You can install directly with pip without cloning the git source code.

### 1. Create a virtual environment

```bash
# Create a virtual environment using conda
conda create -n kalorda python=3.12 -y

# Activate the virtual environment
conda activate kalorda
```

### 2. Install
```bash
pip install kalorda

# Or install with an Aliyun mirror
pip install kalorda -i https://mirrors.aliyun.com/pypi/simple/
```

### 3. Start

```bash
kalorda --port 8800
```

Optional startup parameters:
- `--host`: specify host address, default is `0.0.0.0`
- `--port`: specify port, default is `8800`
- `--gpu-devices`: specify GPU device indices (starting from 0). Default is empty, meaning all GPUs are allowed. Multiple GPUs are separated by commas, e.g. `--gpu-devices 0,1,2`
- `--workers`: specify worker process count (at least 2). Default is `2`
- `--log-level`: specify log level, default is `info`

### 4. Login
```text
Default admin account: admin
Default password: admin123
```

### System and hardware requirements
- Linux OS (on Windows, please install WSL2 Ubuntu)
- Python virtual environment manager (Miniconda3 or uv recommended)
- At least one Nvidia GPU, 6GB VRAM or above; GPU driver and CUDA installed (non-Nvidia GPUs are not supported currently)
- Disk space: ?0GB or more

### Source Installation
If you want to install or debug the project with frontend and backend separated, follow the steps below:

### 1. Clone source
```bash
git clone https://github.com/vlmOCR/Kalorda.git
```

### 2. Install and run
This project contains two parts, located under the project root: `frontend/` and `backend/`.

```text
Kalorda
├── backend/     # backend project
├── frontend/    # frontend project
├── LICENSE      # project license (Apache-2.0)
└── README.md    # github homepage
```

Install and run the backend (vLLM does not support pure Windows; the backend must run on Linux or Windows/WSL2):

```bash
# Enter the backend directory (adjust path to your actual environment)
cd /mnt/d/test/Kalorda/backend/

# Create a virtual environment using conda
conda create -n kalorda python=3.12 -y

# Activate the virtual environment
conda activate kalorda

# Install dependencies
pip install -e .[dev]

# Start (enter src/kalorda directory)
cd /mnt/d/test/Kalorda/backend/src/kalorda/
python -m main --port 8800
```

Install and run the frontend (requires Node.js, OS不限):

```bash
# Enter the frontend directory (adjust path to your actual environment)
cd d:/test/Kalorda/frontend/

# Install dependencies
npm install

# Open the .env.dev file in the frontend directory and set VITE_API_SERVER_URL
# to the running kalorda backend URL.
# Example: VITE_API_SERVER_URL=http://172.18.35.246:8800
# Note: update the IP address to match your backend address.

# Start
npm run dev

# Open the frontend page (default port is 8060; you can change server.port in vite.config.ts)
# Open your browser and visit http://localhost:8060
```

## Build
Build the frontend first:
```bash
# Enter the frontend directory (adjust path to your actual environment)
cd d:/test/Kalorda/frontend/

# Run frontend build
npm run build
```

Built static assets will be saved under `backend/src/kalorda/web_dist` by default,
so the backend build can include them.

Then build the backend:
```bash
# Enter the backend directory (adjust path to your actual environment)
cd /mnt/d/test/Kalorda/backend/

# Install build tool
pip install build

# Run build
python -m build
```

Built wheel files are saved under `backend/dist` by default.
Example install command:
```bash
pip install kalorda-0.1.6-py3-none-any.whl
```

## Contact
Email: [postmaster@vlmocr.com](mailto:postmaster@vlmocr.com)

GitHub Issues: [https://github.com/vlmOCR/Kalorda/issues](https://github.com/vlmOCR/Kalorda/issues)

WeChat: lery2021

<img src="https://raw.githubusercontent.com/vlmOCR/Kalorda/refs/heads/main/frontend/public/wx.png" width="230px" title="WeChat" />

(Scan to add WeChat, note: kalorda, and you will be added to the group.)

## License
Kalorda is open-sourced under the Apache-2.0 license. You are free to use, modify, and distribute this project as long as you comply with the license.

[Apache-2.0](LICENSE)

Copyright (c) 2025-present, Kalorda
