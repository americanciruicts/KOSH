Set objShell = CreateObject("WScript.Shell")
Dim objFSO
Set objFSO = CreateObject("Scripting.FileSystemObject")
Dim CurrentDirectory
CurrentDirectory = objFSO.GetAbsolutePathName(".")
objShell.Run "cmd /c start /b "+CurrentDirectory+"\StockAndPick.bat", 0, True
Set objShell = Nothing