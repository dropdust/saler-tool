#!/usr/bin/env bash
# macOS 签名与公证（T141）：inside-out 签名 → 公证 → 装订
#
# 前置：
#   export DEVELOPER_ID_APPLICATION="Developer ID Application: XXX (TEAMID)"
#   xcrun notarytool store-credentials saler-notary --apple-id … --team-id … --password …
# 用法：packaging/installers/macos/notarize.sh [dist/SalerTool.app]
set -euo pipefail

APP="${1:-backend/dist/SalerTool.app}"
IDENTITY="${DEVELOPER_ID_APPLICATION:?请设置 DEVELOPER_ID_APPLICATION}"
PROFILE="${NOTARY_PROFILE:-saler-notary}"
ENTITLEMENTS="$(dirname "$0")/entitlements.plist"

[ -d "$APP" ] || { echo "缺少 .app：$APP"; exit 1; }

echo "== 0. G2 中间证书检查 =="
security find-certificate -c "Developer ID Certification Authority" >/dev/null \
  || { echo "缺少 Developer ID G2 中间证书：请从 https://www.apple.com/certificateauthority/ 安装并信任"; exit 1; }

echo "== 1. inside-out 签名（二进制 → 框架 → 嵌套包 → 本体）=="
# 1a) Mach-O 二进制与 dylib（由内到外：深路径优先）
find "$APP/Contents" -type f \( -name "*.so" -o -name "*.dylib" -o -perm -111 \) -print0 \
  | sort -zr | while IFS= read -r -d '' f; do
      file "$f" | grep -q "Mach-O" || continue
      codesign --force --timestamp --options runtime \
        --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$f"
    done
# 1b) 嵌套 .app/.framework
find "$APP/Contents" -d \( -name "*.app" -o -name "*.framework" \) | sort -zr | while IFS= read -r -d '' nested; do
  codesign --force --timestamp --options runtime \
    --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$nested"
done
# 1c) 应用本体
codesign --force --timestamp --options runtime \
  --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "== 2. 打包并公证 =="
ZIP="$(dirname "$APP")/$(basename "$APP" .app)-notarize.zip"
ditto -c -k --keepParent "$APP" "$ZIP"
SUBMIT_JSON="$(xcrun notarytool submit "$ZIP" --keychain-profile "$PROFILE" --wait --output-format json)"
echo "$SUBMIT_JSON"

STATUS="$(printf '%s' "$SUBMIT_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
if [ "$STATUS" != "Accepted" ]; then
  echo "公证未通过：status=$STATUS"
  SUBMISSION_ID="$(printf '%s' "$SUBMIT_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
  xcrun notarytool log "$SUBMISSION_ID" --keychain-profile "$PROFILE" || true
  exit 2
fi
echo "notarytool 结果：status: $STATUS"

echo "== 3. 装订与验证 =="
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
spctl -a -vv "$APP"
echo "完成：$APP 已签名、公证并装订"
