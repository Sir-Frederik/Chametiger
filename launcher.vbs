' ChamerTiger Launcher — Asus

Dim oShell
Set oShell = CreateObject("WScript.Shell")

Dim scriptDir
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

Dim pythonw
pythonw = "C:\Users\Asus\AppData\Local\Programs\Python\Python313\pythonw.exe"

oShell.Run """" & pythonw & """ """ & scriptDir & "app.py""", 0, False
WScript.Sleep 2000
oShell.Run """" & pythonw & """ """ & scriptDir & "gui.py""", 0, False

Set oShell = Nothing