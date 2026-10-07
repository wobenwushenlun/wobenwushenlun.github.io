# 人生=模型

一个使用 Python 静态生成器构建、部署到 GitHub Pages 的个人技术博客。文章仍然使用 Markdown 编写，构建环境由 Conda 管理。

## 本地目录

项目位于：

```text
D:\wobenwushenlun.github.io
```

Conda 环境位于项目下的 `.conda` 目录，并已通过 `.gitignore` 排除，不会提交到 GitHub。

## 第一次安装

```powershell
cd D:\wobenwushenlun.github.io
conda env create --prefix .\.conda --file environment.yml
```

如果环境已经存在，需要同步环境时执行：

```powershell
conda env update --prefix .\.conda --file environment.yml --prune
```

## 本地预览

```powershell
cd D:\wobenwushenlun.github.io
.\serve.ps1
```

然后访问：

```text
http://127.0.0.1:4000
```

也可以手动运行：

```powershell
conda run --prefix .\.conda python build.py --serve
```

预览服务会监听源文件变化并自动重新构建。

单独构建并检查站点：

```powershell
conda run --prefix .\.conda python build.py
conda run --prefix .\.conda python validate.py
```

## 写新文章

在 `_posts` 目录创建文件，命名格式为：

```text
YYYY-MM-DD-英文标题.md
```

可以复制 `_drafts/note-template.md` 作为文章模板。完成后把文件移动到 `_posts`，并在文件名中补上发布日期。

## 文章阅读顺序

文章底部的上下篇按阅读顺序连接：以 `categories` 中的第一个分类分组，分类之间按首篇发布时间从早到晚排列；分类内先按文件名中的章节编号排列（如 `llm-agent-03-tool-calling`），无编号文章按发布时间接在编号文章之后。可在文章 front matter 中设置数字 `order` 覆盖自动识别的章节编号。首页和订阅仍按最新发布时间排列。

修改阅读顺序逻辑后，可运行 `.\.conda\python.exe -m unittest test_navigation` 检查章节排序与分类边界。

跨分类时，无论上一分类还是下一分类，都进入目标分类阅读顺序的第一篇。标题摘要下方提供吸顶阅读导航，显示分类和当前篇数；文末保留完整标题导航。跨分类链接使用“上一分类 / 下一分类”标签，与同类上下篇区分。

点击吸顶栏中间的分类名称可展开本分类文章目录，按阅读顺序列出文章并高亮当前篇；可直接选择文章，点击外部或按 Esc 收起目录。

## 访问统计

通过[不蒜子](https://busuanzi.ibruce.info/)统计访问：文章标题上方显示该文章阅读次数（PV），页脚显示全站访问次数（PV）和访客人次（UV）。UV 按服务的规则去重，不等同于真实人数；PV 表示页面访问，不代表读完文章。统计从接入后开始，无法补回历史访问。

`assets/js/analytics.js` 仅在 `_config.yml` 中 `url` 对应域名的 HTTPS 页面加载统计服务，本地预览和其他预览域名不计数。更换正式域名时需同步修改 `url`，统计数据可能重新累计。计数成功返回前隐藏统计项，服务不可用或被浏览器拦截时不会显示虚假的零值。访客浏览器会向第三方不蒜子服务发送统计请求。

## 发布到 GitHub Pages

1. 在 GitHub 创建公开仓库 `wobenwushenlun.github.io`。
2. 将本目录初始化为 Git 仓库并推送到 `main` 分支。
3. 打开仓库的 `Settings → Pages`。
4. 将 `Build and deployment → Source` 设置为 `GitHub Actions`。
5. 等待 `Build and deploy blog to Pages` 工作流执行完成。

站点地址：<https://wobenwushenlun.github.io>

```powershell
git init
git add .
git commit -m "Create 人生=模型 blog"
git branch -M main
git remote add origin https://github.com/wobenwushenlun/wobenwushenlun.github.io.git
git push -u origin main
```

## 常用修改位置

- `_config.yml`：站点名称、介绍、GitHub 地址
- `_posts/`：正式文章
- `_drafts/`：文章草稿和模板
- `_data/works.yml`：作品页内容
- `templates/`：页面模板
- `build.py`：静态站点生成器
- `validate.py`：生成结果与内部链接检查
- `assets/css/style.css`：颜色与视觉样式
- `about.md`：个人介绍
