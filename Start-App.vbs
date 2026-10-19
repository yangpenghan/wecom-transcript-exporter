Option Explicit
Dim fs, shell, root, interpreter
Set fs = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fs.GetParentFolderName(WScript.ScriptFullName)
interpreter = root & "\.venv\Scripts\pythonw.exe"
If Not fs.FileExists(interpreter) Then
  MsgBox "Please use the portable ZIP (Python included), or run Setup.cmd once before opening Start-App.vbs.", 48, "WeCom Transcript Exporter"
  WScript.Quit 1
End If
shell.CurrentDirectory = root
shell.Run Chr(34) & interpreter & Chr(34) & " " & Chr(34) & root & "\desktop_app.py" & Chr(34), 0, False
