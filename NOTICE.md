# 来源与许可

onmyoji-agentflow 整体按 **GNU GPL v3.0 或更新版本** 发布，全文见 [LICENSE](LICENSE)。
Copyright (C) 2026 Shitsuki4 and contributors.

本项目用到了下面两个开源项目的代码、数据和做法。和两个项目的作者都没有关系，也没有得到他们的认可。

## OnmyojiAutoScript（GPL-3.0）

- 来源：https://github.com/nearaura/OnmyojiAutoScript（原仓库 runhey/OnmyojiAutoScript；它又派生自
  LmeSzinc/AzurLaneAutoScript，同为 GPL-3.0）
- 用到的地方：
  - `src/onmyoji_agentflow/device/_oas/`：移植的 `random_rectangle_point`、`insert_swipe`（贝塞尔轨迹）和
    MuMu 12 `external_renderer_ipc.dll` 专用通道（nemu_ipc）。每个文件头写着原始文件和改动。
  - `src/onmyoji_agentflow/device/mumu.py`：MuMu 12 安装目录、多开实例和 adb 端口的查找方式。
  - `src/onmyoji_agentflow/convert/oas.py`：转换器读取 OAS 的模板图和资源描述（只当数据读，不执行它的代码）。
  - `oaf sync` 生成的 `resources/upstream/oas/`：从 OAS 转换来的图片和 YAML，目录里附有 OAS 的 LICENSE，
    每个 YAML 头部写着 `source` 和 `license: GPL-3.0`。

## assttyys_autojs（MIT）

- 来源：https://github.com/zzliux/assttyys_autojs
- 用到的地方：
  - `src/onmyoji_agentflow/device/humanize.py`（`style: assttyys`）：按 `strHashToNum`、`getRegionBiasRnd2`、
    `getNormalRandom` 改写的点击偏移、按压时长和延时。
  - `src/onmyoji_agentflow/convert/assttyys.py`：转换器把 assttyys 的多点比色、找色、点击区域和方案当数据读出来。
  - `src/onmyoji_agentflow/data/resources/assttyys/` 和 `data/workflows/`：由转换器从 assttyys 生成的识别数据和
    内置工作流（御魂、个人结界突破、探索）。
  - `oaf sync` 生成的 `resources/upstream/assttyys/` 和 `resources/upstream/generated/`，目录里附有 assttyys 的 LICENSE。
- 版权声明（按 MIT 许可要求保留）：

```
MIT License

Copyright (c) 2019 Chaos

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 第三方 Python 库

运行时依赖 numpy（BSD）、opencv-python-headless（Apache-2.0）、PyYAML（MIT）、keyring（MIT），
可选 rapidocr_onnxruntime（Apache-2.0）。这些库由 pip 安装，不在本仓库里。

## 商标

「阴阳师」是网易的商标。本项目是非官方工具，和网易没有关系。
