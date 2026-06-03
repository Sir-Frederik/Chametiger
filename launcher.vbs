'    Chametiger Launcher — avvia app.py (tray) e gui.py senza finestra nera

Dim oShell
Set oShell = CreateObject("WScript.Shell")

' Percorso della cartella dove si trova questo file
Dim scriptDir
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

' Avvia il tray in background (pythonw = nessuna console)
oShell.Run "pythonw.exe """ & scriptDir & "app.py""", 0, False

' Pausa 2 secondi
WScript.Sleep 2000

' Avvia la GUI (pythonw per non avere finestra nera)
oShell.Run "pythonw.exe """ & scriptDir & "gui.py""", 0, False

Set oShell = Nothing
