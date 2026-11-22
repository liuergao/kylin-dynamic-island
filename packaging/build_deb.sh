#!/bin/bash
# 麒麟灵动岛（1.2.8 模块化重构版）出包脚本
# 纯 Python，产出 Architecture: all 的 deb；包名 qilin-island，与系统里已装的 fuyu 并存。
#
# 用法:  bash packaging/build_deb.sh                 # 出到 dist/
#        ARCH=arm64 bash packaging/build_deb.sh      # 指定架构（引入 .so 后才需要）
#        OUT=/tmp/deb bash packaging/build_deb.sh    # 指定输出目录
set -e

SRC=$(cd "$(dirname "$0")/.." && pwd)
PKG=qilin-island
NAME=${FILE_NAME:-麒麟灵动岛}
ARCH=${ARCH:-all}
OUT=${OUT:-$SRC/dist}
VER=$(/usr/bin/python3 -c "import sys;sys.path.insert(0,'$SRC');from qilin_island import __version__;print(__version__)")

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/usr/lib/$PKG/qilin_island" \
         "$STAGE/usr/lib/$PKG/resources" \
         "$STAGE/usr/lib/$PKG/doc" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/256x256/apps"

# ── 文档/台账一致性护栏 ─────────────────────────────────────────────
# 1.4.12 出过事故：改了代码和 README 的数字，但 control 描述里那句还是旧数字，
# 三份文本各说各话。代码 md5 有 dpkg -V 兜底，纯文本三份没人兜底，这里补上。
# 护栏 1/2：版本升到 VER 时，README 必须有「## VER 改动」这一段，本脚本的 control
#          描述必须有「 VER 」这一条 bullet（$0 就是脚本自己，不用把自身算进包里）。
grep -q "^## $VER 改动" "$SRC/README.md" \
  || { echo "护栏1 FAIL：README.md 没有「## $VER 改动」这一段" >&2; exit 1; }
grep -q "^ $VER " "$0" \
  || { echo "护栏2 FAIL：build_deb.sh 的 control 描述没有「$VER」这一条 bullet" >&2; exit 1; }
# 护栏 3：README 的 md5 写死在下面。上一次出包时它还是 6cc323…（1.4.14 内容列那版），
#          1.4.15 加了「## 1.4.15 改动」这一段（日历页纵向账本），所以期望值升到
#          acdb6e…。谁改了 README 就必须同时改 control 描述，并把新 md5 记在这里，
#          否则出包停下。
#          期望值随 README 走：每次「真正改了 README」才更新，光改代码不改 README 也会 FAIL，
#          那正是提醒你把改动写进台账的时机。
README_MD5_EXPECT=${README_MD5_EXPECT:-acdb6e785c7058918cff87f10f56a7b2}
README_MD5=$(md5sum "$SRC/README.md" | cut -d" " -f1)
[ "$README_MD5" = "$README_MD5_EXPECT" ] \
  || { echo "护栏3 FAIL：README.md 变了（$README_MD5）但期望值/控制描述没同步" >&2
       echo "  同步 __init__.py + 本脚本 control 描述后，把新 md5 写进 README_MD5_EXPECT" >&2
       exit 1; }

# 代码 + 素材：infra/paths.py 按 <PROJECT_DIR>/resources/assets 找素材，
# 所以 resources 必须和 qilin_island 同级放在 /usr/lib/$PKG 下。
cp -r "$SRC/qilin_island/." "$STAGE/usr/lib/$PKG/qilin_island/"
cp -r "$SRC/resources/." "$STAGE/usr/lib/$PKG/resources/"
cp "$SRC/README.md" "$STAGE/usr/lib/$PKG/doc/"
find "$STAGE" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

cat > "$STAGE/usr/bin/$PKG" <<WRAP
#!/bin/sh
export PYTHONPATH="/usr/lib/$PKG\${PYTHONPATH:+:\$PYTHONPATH}"
# 1.4.4 起固定导出：读屏/无障碍桥不靠用户环境碰运气（待办页标注已落地）
export QT_ACCESSIBILITY=1
exec /usr/bin/python3 -m qilin_island "\$@"
WRAP

cp "$SRC/packaging/$PKG.desktop" "$STAGE/usr/share/applications/"

# 桌面图标由 core/brand.py 现画，和托盘/胶囊用的是同一个来源，不另存一份位图进仓库
QT_QPA_PLATFORM=offscreen PYTHONPATH="$SRC" /usr/bin/python3 - \
  "$STAGE/usr/share/icons/hicolor/256x256/apps/$PKG.png" <<'PY'
import sys
from PyQt5.QtWidgets import QApplication
from qilin_island.core import brand
app = QApplication([])
brand.logo_pixmap(256).save(sys.argv[1])
PY

SIZE=$(du -sk "$STAGE/usr" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<CTRL
Package: $PKG
Version: $VER
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.8), python3-pyqt5
Maintainer: Kylin Island Team
Installed-Size: $SIZE
Description: 麒麟灵动岛 $VER — 桌面顶栏信息岛（模块化重构版）
 待办、专注、饮水、文件中转站、剪贴板、本地音乐、本地日历、系统面板。
 1.3.0 界面居中修正：页签行与内容纵向居中、下拉与数值控件文字居中、
 音乐/饮水/中转站的操作按钮行居中，列表区改为可见卡片。
 1.3.2 收起胶囊居中：图标固定在左侧不随轮播跳动，轮播文字落在岛体中轴，
 文字与图标纵向中线找平。
 1.3.3 修音乐页：sync 里 return 误置于循环内，检测到播放器后曲名/进度/封面/歌词
 永不刷新，现已按周期刷新，播放器掉线才提示未检测到；循环模式按钮改按
 MPRIS 真值显示（此前元组顺序写反，永远停在默认图标）。
 1.4.0 界面焕新（仍零依赖、完全离线）：设计 token 收口（圆角/4px 间距格点/83·167·250·400ms
 与进出场缓动）、岛体形变与进度环/切页淡入改为连续补间、设置页新增「动效」总开关与
 「明暗模式」一键切换、布尔项换成自绘开关控件、通知在无系统通知服务时改为岛内提示条。
 1.4.1 岛本体可见刷新：收起胶囊加 1px 轮廓描边、轮播与时间字号抬到 12/15px，
 展开面板的页签行改为带卡片底的分段控件、选中页签呈 accent 胶囊。
 1.4.2 修未展开态边缘锯齿：合成器判定改问 X 协议 selection 属主，不再把 KWin
 误判成无合成器而走 1-bit 遮罩；面板恢复全不透明，提示条有合成器时不再叠遮罩。
 1.4.3 收起胶囊对齐：轮播文字的居中基准从岛体中轴改为「图标右侧剩余区」
 的中心（此前左右留白 55/86，偏左 15px）；图标墨迹贴住左内边距并补偿
 素材透明边，图标与文字墨迹中线严格重合。
 1.4.4 待办轻量化 + 重复交给日历：待办页只剩输入框+添加与列表（键位：回车添加、
 空格勾选、Delete 删除带撤销），完成判定统一口径，排序未完成在前按添加时间倒序、
 已完成沉底；日历新建日程支持不重复/每天/工作日/每周/每月（月末钳位），
 老待办数据的 due/repeat 不清洗、照旧提醒；启动脚本固定导出 QT_ACCESSIBILITY=1。
 1.4.5 卡片列表与输入框边距对齐：压掉 QListWidget 原生 5px 框与阴影，卡片内边距
 4→2px、条目左右 8→4px、行留白 6→0，待办/剪贴板/文件中转站的白框上下同轴。
 1.4.6 专注页底行重排：开始/暂停贴左、重置贴右、今日统计小字落在行正中，
 三个控件补 accessibleName。
 1.4.7 饮水页重画：杯子改梯形（上宽下窄 + 杯口椭圆），8 只折成 4×2 网格，
 杯区吃掉页面剩余高度。
 1.4.8 修 1.4.7 返工：杯口改成只描边不填色（原先空杯杯口填 card 色，在页面底色
 上露出一块异色补丁）；单杯封顶 44px 宽、竖高比例 1.30、间隙封顶 20px，不再撑成
 桶；统计字号 20 收回 16px。
 1.4.9 文件中转站顶栏重排：「添加文件」移到条目框左上、「清空」新增在右上，提示
 文案只留前半句并单独一行居中，底部原按钮行删除；清空带 5 秒 Toast 撤销，只移条目
 不删磁盘文件，空站时置灰。
 1.4.10 剪贴板每行行尾加一枚小钉子：点钉子切固定（固定项排最前、不参与 30 条淘
 汰），未固定描边、已固定实心；提示文案删掉「右键可固定」，只留「最近 30 条文字，
 点击复制」；长文案的省略改到绘制时按当前行宽现算，不再压住行尾。
 1.4.11 顶栏右上角的「钉」字换成同一枚小钉子图案：与剪贴板行尾共用一份绘制函数，
 未钉住描边、钉住实心且墨色按皮肤现算，按钮热区 26×24；钉住后再点外面不会收起、
 不会折叠（原有 settings.pinned 那条判定，入口没变）。
 1.4.12 待办页删掉列表下面那行「待办 7 · 未完成 3」，下边距 10→6，省出来的 28px
 全给列表（可见行 8→9 行），条目栏拉到页面最下面；条数改挂到列表的读屏名上，
 视觉清爽但信息仍问得到。
 1.4.13 顶栏与剪贴板行尾的图钉改用用户给的 SVG 图标并把颜色改白：本机无 QtSvg，
 新写 infra/svgpath 直接把 path/transform 解析成 QPainterPath；深色皮肤纯白墨（对面板
 底 13.5~18.7），两套浅色皮肤退回正文墨；图案 14/16px（原 12px 只有 21 个墨图像素几乎
 看不见）；顶栏钉住态不再整块铺 accent 底（白对 accent 只有 1.93），改 card 底 + 1px
 accent 描边环 + 白实心，未钉住白描边。固定语义与数据位没动。
 1.4.14 面板里只有一条内容列：新增 core/consts.CONTENT_PAD_X（=0），八个功能页各自的水平
 边距（原本 10~14px）全部归零，顶栏、页签卡、每一页内容的左右缘统一落在面板 x=12..365，
 两侧各 12px 且相等（此前内容只到 24..353，比页签卡缩进 12px，看着就是上下没对齐）；卡片
 列表宽 330→354、剪贴板行 324→348，正文左缘仍与输入框文字同轴，钉子热区仍贴行右缘；
 纵向尺寸一行没动，数据一位没动。
 1.4.15 日历页铺满纵向空间：用户截图里"下面那块空白"是当天 0 条日程时仍占位的日程列表
 （40px 高 + 4px 间距，透明无框）。现在列表只在当天有日程时出现、定高 48（约两行，更多
 走滚动条），空日程日整条收起，省出的 52px 全给月历网格：网格 160→196、每行 23.7→29.7px，
 日期字号随格子 10→11px；顺带结掉 1.3.3 遗留的日历页纵向挤压（旧账本网格下限 160 + 列表
 下限 40 = 200 装不进可用的 192，实测叠了 4px），改成 144 + 48 = 192 闭合后两种状态重叠
 都是 0px。内容列、月份行、按钮行、数据一位没动。
 完全离线运行。
CTRL

find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/usr/bin/$PKG"

mkdir -p "$OUT"
DEB="$OUT/${NAME}_${VER}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$DEB" >/dev/null
ls -lh "$DEB"
