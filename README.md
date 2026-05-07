# 1688 商品主图爬虫

从 1688 (m.1688.com / detail.1688.com) 抓取商品主图轮播图。

## 三层鲁棒策略

任何一层成功就退出，单点失败不会打死整个脚本。

| 层 | 策略 | 何时生效 |
|---|---|---|
| Layer 1 | `httpx` 直连 `detail.1688.com` HTML，正则抓 `window.runParams` JSON | IP 干净时最快 |
| Layer 2 | Playwright + 持久化 Chrome profile (cookie 跨次复用) + stealth patch | Layer 1 被风控时 |
| Layer 3 | OpenCV 模板匹配定位拼图缺口 + bezier 曲线拖动 | Layer 2 撞到滑块时自动调用 |

**重要**: Alibaba x5sec 是工业级反爬。脚本尽全力，但拼图滑块自动通过率受 IP / 历史行为影响很大。**第一次跑过滑块后的 cookie 会写入 `./.chrome_profile/`，后续几小时到几天内同 ID 通常能直接放行**。

## 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

依赖: `playwright`, `httpx`, `opencv-python-headless`, `numpy`

## 用法

```bash
# 方式 A: 传 offer ID
python scrape_1688.py 1040900910125

# 方式 B: 传完整 URL (包括被风控后的 punish URL)
python scrape_1688.py "https://m.1688.com/offer/1040900910125.html"
python scrape_1688.py "https://m.1688.com//offer/1040900910125.html/_____tmd_____/punish?x5secdata=...&x5step=1"
```

图片保存到 `./images/<offer_id>/<offer_id>_NN.jpg`。

### 选项

| flag | 默认 | 说明 |
|---|---|---|
| `-o`, `--output` | `./images/<offer_id>/` | 输出目录 |
| `--headful` | False | 显示浏览器窗口 (调试用) |
| `--no-api` | False | 跳过 Layer 1，直接走浏览器 |
| `--profile DIR` | `./.chrome_profile` | 持久化 Chrome profile 目录 |
| `--timeout SEC` | 30 | 单步等待秒数 |
| `--debug-slider` | False | 把滑块背景/拼块/匹配结果 PNG 转储到 `./debug_slider/` |

### 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 参数错误 / 网络错误 / 找不到图片字段 |
| 2 | 滑块连续 3 次都没解开 |
| 3 | API 和浏览器都试过，仍没拿到图 |

## 工作原理

### Layer 1 (API 直连)

`detail.1688.com/offer/{id}.html` 桌面页面在 HTML 里嵌了 `window.runParams = {...}`，里面就有完整的图片列表。脚本用一个 brace-counting 的解析器抠出 JSON，递归找带 `image|img|pic|photo|gallery` 字眼的 key 下的 URL 数组。这条路 0 浏览器开销，IP 干净时秒出。

### Layer 2 (持久化浏览器)

如果 Layer 1 被 302 到 punish 页或返回的 HTML 里没图，开 Playwright Chromium。关键点:

- `launch_persistent_context` 绑定 `./.chrome_profile/`，cookie / localStorage 全部跨次保留
- 移动端模拟 (iPhone viewport + Mobile Safari UA)
- `add_init_script` 注入 stealth patch: `navigator.webdriver`, `navigator.plugins`, `navigator.languages`, `chrome` 对象, `permissions.query`, WebGL vendor

页面里直接 `page.evaluate` 跑 JS 抠图，字段路径覆盖 `_DATA_` / `__INIT_DATA__` / `runParams` / DOM 兜底。

### Layer 3 (OpenCV 滑块求解)

1688 的 x5sec 是拼图式滑块 (背景 + 小拼块，要拖到缺口位置)。

1. 选择器优先级在 iframe 和主页面都搜 (`iframe[src*="punish|x5sec|baxia|captcha"]` 优先)
2. 拿到背景元素和拼块元素的 PNG (canvas 直接 `element.screenshot()`，img 用 src 下载)
3. 双方都走 `cv2.Canny` 边缘 + `cv2.matchTemplate` 模板匹配 + `cv2.minMaxLoc` 找最大相似度，得到缺口左上角 X 坐标
4. 转换成页面坐标，减去拼块当前 X，得到拖动距离
5. 物理模型生成 track: 70% 加速 + 30% 减速 + 末端 ±2-5px 过冲再回拉，每步 5-22ms 随机间隔，Y 轴 ±1.5px 抖动
6. `mouse.down()` → 循环 `mouse.move(steps=1)` → `mouse.up()`
7. 等 2-3 秒看 button 是否消失 / URL 是否离开 punish；最多 3 次

加 `--debug-slider` 时会把 `bg.png`, `piece.png`, `match.png` (红框标出匹配位置) 写到 `./debug_slider/` 方便人眼检查。

### 图片 URL 升清

1688 经常返回 `_400x400q90.jpg` / `_60x60.jpg` / `.summ.jpg` 这种缩略图后缀。脚本统一用正则去后缀拿原图。

## 局限

- 只抓主图轮播 (用户需求)。SKU 颜色小图、详情页大图不在范围
- 没有断点续传 / 批量爬取 (需要可以加)
- 没集成 2captcha 等付费打码 (Layer 3 失败就直接退出)
- mtop API sign 算法没手撸，Layer 1 走 HTML 路线规避

## 文件清单

```
.
├── README.md
├── requirements.txt
├── scrape_1688.py        # 全部逻辑，~500 行
├── .gitignore
├── images/               # 输出 (gitignore)
└── .chrome_profile/      # Playwright 持久化 profile (gitignore)
```
