Option Explicit

Dim shell, fso, projectDir, launcher, pythonw
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = projectDir & "\bot_launcher_ui.py"
pythonw = ResolvePython(projectDir)

If pythonw = "" Then
    MsgBox "Python was not found. Create .venv, install Python, or add Python to PATH.", vbCritical, "Discord Music Bot"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectDir
shell.Run """" & pythonw & """ """ & launcher & """", 0, False

Function ResolvePython(projectDir)
    Dim candidate
    candidate = projectDir & "\.venv\Scripts\pythonw.exe"
    If fso.FileExists(candidate) Then
        ResolvePython = candidate
        Exit Function
    End If

    candidate = projectDir & "\.venv\Scripts\python.exe"
    If fso.FileExists(candidate) Then
        ResolvePython = candidate
        Exit Function
    End If

    candidate = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"
    If fso.FileExists(candidate) Then
        ResolvePython = candidate
        Exit Function
    End If

    candidate = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\python.exe"
    If fso.FileExists(candidate) Then
        ResolvePython = candidate
        Exit Function
    End If

    candidate = FindOnPath("pythonw.exe")
    If candidate <> "" Then
        ResolvePython = candidate
        Exit Function
    End If

    candidate = FindOnPath("python.exe")
    If candidate <> "" Then
        ResolvePython = candidate
        Exit Function
    End If

    ResolvePython = ""
End Function

Function FindOnPath(exeName)
    Dim envPath, parts, i, candidate
    envPath = shell.ExpandEnvironmentStrings("%PATH%")
    parts = Split(envPath, ";")
    For i = 0 To UBound(parts)
        If parts(i) <> "" Then
            candidate = parts(i) & "\" & exeName
            If fso.FileExists(candidate) Then
                FindOnPath = candidate
                Exit Function
            End If
        End If
    Next
    FindOnPath = ""
End Function
