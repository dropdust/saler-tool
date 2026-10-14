; Inno Setup 安装脚本（T140）：以 PyInstaller onedir 产物为输入
; 用法：先完成 packaging/saler.spec 冻结（backend/dist/SalerTool/），再：
;   iscc packaging/installers/windows/inno.iss
; 说明：
; - WebView2 运行时 Win10/11 系统自带；极老系统提示用户安装 Evergreen 运行时
; - 卸载默认保留用户数据（数据目录在 %LOCALAPPDATA%，不清除）；提供可选"删除数据"提示

#define MyAppName "销售获客工具"
; 版本默认 0.1.0；CI 以 iscc /DMyAppVersion=<tag 去 v> 覆盖（见 build.yml）
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Saler"
#define MyAppExeName "SalerTool.exe"
#define DistDir "..\..\backend\dist\SalerTool"

[Setup]
AppId={{8F2A6C2E-4B1D-4C7E-9A2B-7E5C0B1D5F31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SalerTool
DefaultGroupName={#MyAppName}
OutputDir=..\..\backend\dist\installer
OutputBaseFilename=SalerTool-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; 安装前关闭正在运行的实例由 [Code] 段处理

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 仅清理应用目录本体；用户数据目录（%LOCALAPPDATA%\Saler）默认保留

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  { 幂等升级：尝试结束旧实例（失败不阻断） }
  Exec('taskkill.exe', '/IM {#MyAppExeName} /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
