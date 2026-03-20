[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName=桥牌叫牌练习系统
AppVersion=1.0.0
AppPublisher=Bridge Card
AppPublisherURL=https://github.com/yourusername/bidding-system
AppSupportURL=https://github.com/yourusername/bidding-system/issues
DefaultDirName={autopf}\桥牌叫牌练习
DefaultGroupName=桥牌叫牌练习
AllowNoIcons=yes
LicenseFile=LICENSE.txt
InfoBeforeFile=README.txt
OutputDir=installer
OutputBaseFilename=桥牌叫牌练习_安装程序
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\桥牌叫牌练习.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "JF约定.docx"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "Deep Finesse 2014 v2\*"; DestDir: "{app}\Deep Finesse 2014 v2"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: DirExists(ExpandConstant('Deep Finesse 2014 v2'))

[Dirs]
Name: "{app}\logs"; Permissions: users-modify

[Icons]
Name: "{group}\桥牌叫牌练习"; Filename: "{app}\桥牌叫牌练习.exe"
Name: "{group}\配置API密钥"; Filename: "notepad.exe"; Parameters: "{app}\.env"
Name: "{group}\使用说明"; Filename: "{app}\README.txt"
Name: "{group}\{cm:UninstallProgram,桥牌叫牌练习}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\桥牌叫牌练习"; Filename: "{app}\桥牌叫牌练习.exe"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\桥牌叫牌练习"; Filename: "{app}\桥牌叫牌练习.exe"; Tasks: quicklaunchicon

[Run]
Filename: "notepad.exe"; Parameters: "{app}\.env.example"; Description: "查看API配置示例"; Flags: postinstall skipifsilent
Filename: "{app}\桥牌叫牌练习.exe"; Description: "{cm:LaunchProgram,桥牌叫牌练习}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
var
  EnvFile: String;
begin
  Result := True;
  
  EnvFile := ExpandConstant('{app}\.env');
  
  if not FileExists(EnvFile) then
  begin
    if MsgBox('检测到这是首次安装。' + #13#10 + #13#10 + 
              '本程序需要配置 DeepSeek API 密钥才能使用。' + #13#10 + #13#10 +
              '安装完成后，请：' + #13#10 +
              '1. 将 .env.example 复制为 .env' + #13#10 +
              '2. 编辑 .env 文件，填入您的 API 密钥' + #13#10 + #13#10 +
              '是否继续安装？', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvExample, EnvFile: String;
begin
  if CurStep = ssPostInstall then
  begin
    EnvExample := ExpandConstant('{app}\.env.example');
    EnvFile := ExpandConstant('{app}\.env');
    
    if FileExists(EnvExample) and not FileExists(EnvFile) then
    begin
      FileCopy(EnvExample, EnvFile, False);
    end;
  end;
end;
