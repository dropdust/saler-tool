# macOS 打包说明（T140/T141）

## 1. 冻结

```bash
cd frontend && pnpm build && cd ../backend
uv run pyinstaller ../packaging/saler.spec --noconfirm
# 产出 backend/dist/SalerTool/（onedir）
```

## 2. 组装 .app 与签名（inside-out）

对嵌套二进制**由内向外**逐个签名，再签 .app 本体：
（完整脚本见 `notarize.sh`，签名顺序：`Python` 等框架 → `.so/.dylib` → 内嵌二进制 → `SalerTool.app`）

```bash
codesign --force --timestamp --options runtime \
  --sign "$DEVELOPER_ID_APPLICATION" \
  --entitlements entitlements.plist \
  "dist/SalerTool.app"
```

- `entitlements.plist` 最小集：`com.apple.security.cs.allow-unsigned-executable-memory`（Python 运行所需）、如需网络无特别项。
- **G2 中间证书**：确认钥匙串中有 "Developer ID Certification Authority"（G2），否则 `codesign --timestamp` 将失败。
- 验证：`codesign --verify --deep --strict --verbose=2 dist/SalerTool.app` 与 `spctl -a -vv dist/SalerTool.app`（应显示 "accepted, source=Notarized Developer ID"）。

## 3. 公证（notarize）与装订（staple）

```bash
ditto -c -k --keepParent dist/SalerTool.app dist/SalerTool.zip
xcrun notarytool submit dist/SalerTool.zip --keychain-profile "saler-notary" --wait
# 解析结果：XML/JSON 中 status 必须为 "Accepted"
xcrun stapler staple dist/SalerTool.app
xcrun stapler validate dist/SalerTool.app
```

## 4. DMG 制作（拖拽安装）

```bash
mkdir -p dist/dmg-root
cp -R dist/SalerTool.app dist/dmg-root/
ln -s /Applications dist/dmg-root/Applications
hdiutil create -volname "销售获客工具" -srcfolder dist/dmg-root \
  -ov -format UDZO dist/installer/SalerTool-0.1.0-arm64.dmg
codesign --force --timestamp --sign "$DEVELOPER_ID_APPLICATION" dist/installer/SalerTool-0.1.0-arm64.dmg
xcrun stapler staple dist/installer/SalerTool-0.1.0-arm64.dmg
```

## 5. 冒烟

首次运行（Gatekeeper 放行确认）后跑 quickstart S1 / S6 / S10 并记录结论。
