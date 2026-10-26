# Changelog

## 1.1.5

- Augment badges now hide when another program is in the foreground (for example after Alt-Tab) and come back as soon as the game is focused again. Clicking the assistant's own panel does not hide them.
- Small samples are now labelled as reference only, including the case where all three cards on screen have fewer than 1000 games. Scores, win-rate ranks and the recommended pick are unchanged.
- Summoner spells now include every combination with at least 3% pick rate and 1000 games, sorted by win rate, up to three. When none qualifies, the most-played combination is still shown.
- If the three cards are clearly on screen but nothing can be recognised for a sustained period, the app now says so: one notification and one log line per game. It stays quiet for a single missed read, a short fade, one recognised card, a missing language pack or a game in the background, and it takes no extra screenshots.
- Card recognition retries a transient miss instead of dropping the offer, and a saved card layout that is malformed, outside the screen or overlapping is now rejected instead of being used.
- Bundled stats refreshed: patch 16.21, sample up to 26 October 2026, 5.38 million valid matches.
- No change to the recognition pipeline's resolution handling, no renderer rewrite, no new network hosts and no telemetry of any kind.

## 1.1.4

- Stats downloads stay inside the app's own data folder: a tampered download can no longer place files elsewhere.
- Automatic screenshots now happen only in debug mode; an ordinary run saves none.
- If Windows is missing the text-recognition language pack, the app now says so instead of quietly recognising nothing.
- The portable build's note is English, links this repository and says updates are manual.
- The privacy notes now describe what the app actually stores and sends.

## 1.1.3

- The Windows installer is English throughout: the wizard, the Start Menu folder, both shortcut names, the uninstall entry, and the name shown in Apps & features. All of it was still Chinese, inherited from upstream.
- The installer's publisher and its help/update links point at this repository instead of upstream's.
- The release workflow is English, so future releases no longer publish Chinese titles and notes.

No changes to the application itself.

## 1.1.2

- 修复部分分辨率下三选一认不出卡：现在不管游戏是多少分辨率，识别前都把标题区域缩放到同样的大小（1366×768 这类小分辨率也不再漏认一张）
- 1920×1080 实机验证：三选一三个标签、选英雄识别都正常；4K 同样正常
- 更多详情见 GitHub

## 1.1.1

- 内置 16.21 正式服数据（约 108 万局）
- 新电脑第一次打开就能认出选的英雄
- 召唤师技能：显示出场多的两组，按胜率排
- 三选一识别更稳定
- 修复秒退、对局结束后还显示上一把的英雄
- 修复移动窗口或换分辨率后标签位置不对
- 分段改成娱乐 / 中分 / 前 5%（目前都用全体数据）
- 更多详情见 GitHub

完整更新内容：

- 内置 16.21 正式服数据（约 108 万局）
- 新电脑第一次打开就能认出选的英雄，不用再等头像下载
- 召唤师技能：显示出场多的两组，按胜率排
- 三选一识别更稳定
- 修复秒退后再进，还显示上一把的英雄
- 修复对局结束后，还显示上一局的英雄和推荐
- 修复移动窗口或换分辨率后，标签位置不对
- 进游戏后才打开助手时，会提示手动选择英雄；搜索框加了确认按钮
- 五杀乐队的卡写明强化哪个技能，并显示这个英雄选 Q/W/E/R 的胜率
- 新海克斯样本少时，显示全英雄胜率和本英雄局数
- 大厅里的助手图标挪到头像右边
- 录屏、直播可以显示浮窗
- 分段改成娱乐 / 中分 / 前 5%（样本还少，目前各分段都用全体数据）
- 小屏幕或高缩放时，主界面能完整显示
- 设置页更简洁，新增「帮助改善软件」开关

## 1.1.0

- 适配海斗 4.0
- 修复掉帧
- 支持外服
- 修复深色模式
- 修复缩放问题，标签可自选在卡片下方
- 修复退出问题

## 1.0.0

- 第一个正式版本。
- 选英雄时自动识别你和队友的英雄，显示胜率和评级。
- 海克斯三选一时，给出这个英雄拿每个海克斯的胜率和排名，推荐选哪个。
- 显示官方出装（多套）和加点。
- 可以切换娱乐、中分、高分、顶尖局的数据。
- 设置里可以查自己的水平（区内前百分之几），自动选对应分段。
