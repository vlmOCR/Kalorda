<p align="center">
<img src="https://raw.githubusercontent.com/vlmOCR/Kalorda/refs/heads/main/frontend/public/logo.png" alt="Kalorda" align="center" style="margin: 20px 20px -20px 0;">
</p>
<h1 align="center" style="font-size: 60px;"><b>Kalorda</b></h1>
<p align="center" style="font-size: 25px;"><b>轻量vlmOCR模型一站式微调平台</b></p>
<p align="center">
<a href="https://github.com/modelscope/ms-swift" target="_blank"><img src="https://img.shields.io/badge/modelscope-ms--swift-red"></a>
<a href="https://github.com/vllm-project/vllm" target="_blank"><img src="https://img.shields.io/badge/vLLM-blue"></a>
<a href="https://vuejs.org/"><img src="https://img.shields.io/badge/Vue3+Vite-red"></a> 
<a href="https://github.com/vlmOCR/Kalorda"><img src="https://img.shields.io/badge/github-repo-blue?logo=github"></a>
<a href="https://pypi.org/project/kalorda"><img src="https://img.shields.io/badge/pypi-v0.1.6-orange"></a>
<a href="https://kalorda.vlmocr.com"><img src="https://img.shields.io/badge/Website-online-yellow"></a> 
</p>

Kalorda是一个轻量vlmOCR模型微调集成平台，前端采用Typescript+Vue3+Vite，后端采用Python+FastAPI+ms-swift+vLLM构建，提供针对主流轻量vlmOCR模型的数据二次标注、微调训练、对比测试等一站式综合解决方案。

## 🚩安装使用

### 1、新建虚拟环境

```
# 使用 conda 新建虚拟环境
conda create -n kalorda python=3.12 -y

# 激活（切换）虚拟环境
conda activate kalorda
```
### 2、安装命令
```
pip install kalorda

# 或指定阿里云镜像源进行安装
pip install kalorda -i https://mirrors.aliyun.com/pypi/simple/
```

### 3、启动命令

```
kalorda --port 8800
```
可选启动参数：
- `--host`：指定主机地址，默认值为 `0.0.0.0`
- `--port`：指定端口号，默认值为 `8800`
- `--gpu-devices`：指定允许使用的GPU设备索引（从0开始），默认值为空表示不限制（即全部GPU都可使用），多个GPU索引用逗号分隔，例如 `--gpu-devices 0,1,2`
- `--workers`：指定工作进程数（至少要2个工作进程），默认值为 `2`
- `--log-level`：指定日志级别，默认值为 `info`

### 4、登录账号
```
初始管理员账号Admin密码admin123
```

### 系统和硬件条件：
- Linux操作系统（Windows下请安装wsl2 ubuntu子系统）
- Python虚拟环境管理工具（推荐使用miniconda3或uv）
- 至少一张Nvidia GPU显卡，显存16G或以上，已安装显卡驱动及CUDA（非Nvidia显卡当前暂不支持，等后续）
- 硬盘空间：50GB或以上


## 💡联系交流
邮箱：[postmaster@vlmocr.com](mailto:postmaster@vlmocr.com)

GitHub/Issues：[https://github.com/vlmOCR/Kalorda/issues](https://github.com/vlmOCR/Kalorda/issues)

微信：llery2021

<img src="https://raw.githubusercontent.com/vlmOCR/Kalorda/refs/heads/main/frontend/public/wx.png" width="230px" title="微信" />

(扫码添加微信，备注：kalorda，邀您加入群聊)

## 📜License
Kalorda项目基于Apache-2.0协议开源，您可以在遵守协议的前提下自由使用、修改和分发本项目。

[Apache-2.0](LICENSE)

Copyright (c) 2025-present, Kalorda