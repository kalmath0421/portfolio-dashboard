' 포트폴리오 대시보드 — 숨김 실행 런처
' 콘솔 창 없이 백그라운드로 Streamlit 실행 후 브라우저 자동 오픈.
' 종료하려면 stop.bat 더블클릭.

Option Explicit

Dim WshShell, FSO, scriptDir, batPath
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
scriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
batPath = scriptDir & "\run.bat"

If Not FSO.FileExists(batPath) Then
    MsgBox "run.bat 을 찾을 수 없습니다: " & batPath, vbCritical, "포트폴리오 대시보드"
    WScript.Quit 1
End If

' 이미 실행 중인지 8501 포트 확인 (간단한 방식: 브라우저로 바로 시도)
Dim http, alreadyRunning
alreadyRunning = False
On Error Resume Next
Set http = CreateObject("MSXML2.XMLHTTP")
http.Open "GET", "http://localhost:8501/_stcore/health", False
http.Send
If Err.Number = 0 And http.Status = 200 Then
    alreadyRunning = True
End If
On Error Goto 0

If Not alreadyRunning Then
    ' 0 = 창 숨김, False = 백그라운드 실행
    WshShell.CurrentDirectory = scriptDir
    WshShell.Run "cmd /c """ & batPath & """", 0, False
    ' 서버가 뜰 때까지 최대 30초 대기
    Dim elapsed
    elapsed = 0
    Do While elapsed < 30
        WScript.Sleep 1500
        elapsed = elapsed + 1.5
        On Error Resume Next
        http.Open "GET", "http://localhost:8501/_stcore/health", False
        http.Send
        If Err.Number = 0 And http.Status = 200 Then Exit Do
        On Error Goto 0
    Loop
End If

' 브라우저로 열기 (기본 브라우저 사용)
WshShell.Run "http://localhost:8501", 1, False
