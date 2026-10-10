# Windows 代码签名（T141）

发布阶段对**安装器与主程序 exe** 签名。推荐 **Azure Trusted Signing**（约 $10/月，EV 等效、免 HSM 采购）。

## 1. 前置

- Azure 订阅 + Trusted Signing 账户与证书配置（Individual 需身份验证；Organization 需组织验证）；
- `signtool.exe`（Windows SDK）或 Azure 的 `trusted-signing-cli`。

## 2. 签名（signtool 直连 Trusted Signing）

```powershell
signtool sign /v /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 `
  /dlib "$env:AZURE_CODESIGNING_DLIB" /dmdf metadata.json `
  backend\dist\SalerTool\SalerTool.exe

signtool sign /v /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 `
  /dlib "$env:AZURE_CODESIGNING_DLIB" /dmdf metadata.json `
  backend\dist\installer\SalerTool-Setup-0.1.0.exe
```

`metadata.json`（Trusted Signing 必填）示例：

```json
{
  "Endpoint": "https://eus.codesigning.azure.net/",
  "CodeSigningAccountName": "<account>",
  "CertificateProfileName": "<profile>",
  "ExcludeCredentials": []
}
```

## 3. 校验

```powershell
signtool verify /pa /v backend\dist\SalerTool\SalerTool.exe
```

## 4. 备选与注意

- 未签名首发的代价：SmartScreen 需"预热"（安装量累积后提示消失）。接受该路径时也应在安装器 README 说明"更多信息 → 仍要运行"。
- EV 证书（含 Trusted Signing）签名后 SmartScreen 立即放行。
- 签名必须在**冻结完成之后**、**制作安装器之前**对 exe 签名；安装器本身最后再签。
- CI 集成：在 `build.yml` 的 Windows 任务中经 `azure/login` + `trusted-signing-action` 注入，仅发布标签触发。
