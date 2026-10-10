Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

!ifndef APP_DIR
  !error "APP_DIR is required"
!endif
!ifndef OUTPUT_FILE
  !error "OUTPUT_FILE is required"
!endif
!ifndef UNINSTALL_MANIFEST
  !error "UNINSTALL_MANIFEST is required"
!endif

Name "TravelDesk Whisper"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\TravelDeskWhisper"
InstallDirRegKey HKCU "Software\TravelDeskWhisper" "InstallDir"
RequestExecutionLevel user
SetCompressor zlib
CRCCheck force
ManifestDPIAware true
VIProductVersion "1.1.0.0"
VIAddVersionKey /LANG=1033 "ProductName" "TravelDesk Whisper"
VIAddVersionKey /LANG=1033 "CompanyName" "TravelDesk"
VIAddVersionKey /LANG=1033 "FileDescription" "Instalador de TravelDesk Whisper"
VIAddVersionKey /LANG=1033 "FileVersion" "1.1.0"
VIAddVersionKey /LANG=1033 "LegalCopyright" "TravelDesk"

!define MUI_ICON "traveldesk-whisper.ico"
!define MUI_UNICON "traveldesk-whisper.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Instalar TravelDesk Whisper 1.1.0"
!define MUI_WELCOMEPAGE_TEXT "Dicta en tus aplicaciones con Ctrl+Espacio.$\r$\n$\r$\nEl modelo de voz está incluido. El dictado funciona localmente, sin API key y sin conexión a internet.$\r$\n$\r$\nSe instalará para tu usuario de Windows y se crearán accesos directos. Cierra TravelDesk Whisper antes de actualizarlo."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\TravelDeskWhisper.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir TravelDesk Whisper"
!define MUI_FINISHPAGE_TEXT "La instalación está completa.$\r$\n$\r$\nColoca el cursor donde quieres escribir, mantén Ctrl+Espacio, habla y suelta.$\r$\n$\r$\nEl icono de la bandeja de Windows permite mostrar, ocultar o cerrar el dictado."
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Spanish"

Function .onInit
  SetShellVarContext current
  ${IfNot} ${IsNativeAMD64}
    MessageBox MB_ICONSTOP "Esta versión requiere Windows x64 (Intel o AMD)."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "Esta versión requiere Windows 10 u 11."
    Abort
  ${EndIf}
FunctionEnd

Section "TravelDesk Whisper" MainSection
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  SetOverwrite on
  File "${APP_DIR}\TravelDeskWhisper.exe"
  File "${APP_DIR}\README.md"
  File "${APP_DIR}\.env.example"
  File "${APP_DIR}\requirements-windows.lock"
  File "${APP_DIR}\release.json"
  SetOutPath "$INSTDIR\_internal"
  File /r "${APP_DIR}\_internal\*.*"
  SetOutPath "$INSTDIR\models"
  File /r "${APP_DIR}\models\*.*"
  SetOutPath "$INSTDIR\licenses"
  File /r "${APP_DIR}\licenses\*.*"
  SetOutPath "$INSTDIR"
  SetOverwrite off
  File "${APP_DIR}\config.json"
  SetOverwrite on
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\TravelDesk Whisper"
  CreateShortcut "$SMPROGRAMS\TravelDesk Whisper\TravelDesk Whisper.lnk" "$INSTDIR\TravelDeskWhisper.exe"
  CreateShortcut "$DESKTOP\TravelDesk Whisper.lnk" "$INSTDIR\TravelDeskWhisper.exe"
  WriteRegStr HKCU "Software\TravelDeskWhisper" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelDeskWhisper" "DisplayName" "TravelDesk Whisper"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelDeskWhisper" "DisplayVersion" "1.1.0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelDeskWhisper" "Publisher" "TravelDesk"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelDeskWhisper" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelDeskWhisper" "DisplayIcon" "$INSTDIR\TravelDeskWhisper.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelDeskWhisper" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelDeskWhisper" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelDeskWhisper" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelDeskWhisper" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  ; Delete only known payload files; preserve user configuration and data.
  !include "${UNINSTALL_MANIFEST}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\TravelDesk Whisper.lnk"
  Delete "$SMPROGRAMS\TravelDesk Whisper\TravelDesk Whisper.lnk"
  RMDir "$SMPROGRAMS\TravelDesk Whisper"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelDeskWhisper"
  DeleteRegKey HKCU "Software\TravelDeskWhisper"
SectionEnd
