// Hefex Labs: export ODB++ from an Altium Designer PCB project.
//
// Runs inside the open Altium instance, started by the agent with
//   X2.EXE -RScriptingSystem:RunScript(ProjectName="<Kit>\HefexScripts.PrjScr"|ProcName="HefexOdbExport.pas>ExportOdb")
// Reads <Kit>\export.ini, writes every step to <Kit>\export_status.txt.
//
// export.ini:
//   [Export]
//   Project=C:\path\Board.PrjPcb   ; required
//   AddOutJob=0                    ; 1 = the customer agreed to add Hefex.OutJob
//   AllowUnsaved=0                 ; 1 = export even with unsaved documents
//
// Unsaved project documents stop the export (error: unsaved_documents, each
// one listed as "unsaved: <path>"), so nobody orders a state they did not save,
// unless AllowUnsaved=1.
//
// Order: use an ODB++ output job that is already part of the project; only
// when there is none and AddOutJob=1, copy Hefex.OutJob next to the project,
// add it and save the project. Every step is inside Try/Except: an unhandled
// runtime error would leave the script paused in the debugger, and Altium then
// refuses every later script until "Stop Debugging" (X2.EXE -REditScript:Stop).

Const
    Kit        = 'C:\Users\Public\Documents\Hefex\altium\';
    StatusFile = 'C:\Users\Public\Documents\Hefex\altium\export_status.txt';
    ConfigFile = 'C:\Users\Public\Documents\Hefex\altium\export.ini';
    Template   = 'C:\Users\Public\Documents\Hefex\altium\Hefex.OutJob';
    MaxIndex   = 64;

Procedure Log(Msg : String);
Var F : TextFile;
Begin
    AssignFile(F, StatusFile);
    If FileExists(StatusFile) Then Append(F) Else Rewrite(F);
    WriteLn(F, Msg);
    CloseFile(F);
End;

Function FindProject(Path : String) : IProject;
Var Workspace : IWorkspace; I : Integer; P : IProject;
Begin
    Result := Nil;
    Workspace := GetWorkspace;
    For I := 0 To Workspace.DM_ProjectCount - 1 Do
    Begin
        P := Workspace.DM_Projects(I);
        If LowerCase(P.DM_ProjectFullPath) = LowerCase(Path) Then Result := P;
    End;
End;

// The first medium of a GeneratedFiles type that an ODB output of the job is
// enabled for, '' when the job has no such output.
Function OdbMedium(OutJobPath : String) : String;
Var Ini : TIniFile; G, K, J : Integer; Section, Medium : String;
Begin
    Result := '';
    Ini := TIniFile.Create(OutJobPath);
    Try
        For G := 1 To MaxIndex Do
        Begin
            Section := 'OutputGroup' + IntToStr(G);
            If Not Ini.SectionExists(Section) Then Break;
            For K := 1 To MaxIndex Do
            Begin
                If Ini.ReadString(Section, 'OutputType' + IntToStr(K), '') = '' Then Break;
                If (Ini.ReadString(Section, 'OutputType' + IntToStr(K), '') = 'ODB')
                    And (Ini.ReadString(Section, 'OutputEnabled' + IntToStr(K), '0') = '1') Then
                    For J := 1 To MaxIndex Do
                    Begin
                        Medium := Ini.ReadString(Section, 'OutputMedium' + IntToStr(J), '');
                        If Medium = '' Then Break;
                        If (Ini.ReadString(Section, 'OutputMedium' + IntToStr(J) + '_Type', '') = 'GeneratedFiles')
                            And (Ini.ReadString(Section, 'OutputEnabled' + IntToStr(K) + '_OutputMedium' + IntToStr(J), '0') = '1')
                            And (Result = '') Then
                            Result := Medium;
                    End;
            End;
        End;
    Finally
        Ini.Free;
    End;
End;

// An output job of the project with an enabled ODB output, '' when none.
Function ProjectOdbJob(Project : IProject) : String;
Var I : Integer; Path : String;
Begin
    Result := '';
    For I := 0 To Project.DM_LogicalDocumentCount - 1 Do
    Begin
        Path := Project.DM_LogicalDocuments(I).DM_FullPath;
        If (Result = '') And (LowerCase(ExtractFileExt(Path)) = '.outjob') And (OdbMedium(Path) <> '') Then
            Result := Path;
    End;
End;

// Logs every project document that is open with unsaved changes; returns their number.
Function UnsavedDocuments(Project : IProject) : Integer;
Var I : Integer; Path : String; D : IServerDocument;
Begin
    Result := 0;
    For I := 0 To Project.DM_LogicalDocumentCount - 1 Do
    Begin
        Path := Project.DM_LogicalDocuments(I).DM_FullPath;
        If Client.IsDocumentOpen(Path) Then
        Begin
            D := Client.GetDocumentByPath(Path);
            If (D <> Nil) And D.Modified Then
            Begin
                Log('unsaved: ' + Path);
                Result := Result + 1;
            End;
        End;
    End;
End;

Function AddHefexJob(Project : IProject) : String;
Var Lines : TStringList; Target : String; ProjDoc : IServerDocument;
Begin
    Target := ExtractFilePath(Project.DM_ProjectFullPath) + 'Hefex.OutJob';
    If Not FileExists(Target) Then
    Begin
        Lines := TStringList.Create;
        Try
            Lines.LoadFromFile(Template);
            Lines.SaveToFile(Target);
        Finally
            Lines.Free;
        End;
    End;
    Project.DM_AddSourceDocument(Target);
    ProjDoc := Client.GetDocumentByPath(Project.DM_ProjectFullPath);
    If ProjDoc <> Nil Then ProjDoc.DoFileSave('');
    Result := Target;
End;

Procedure ExportOdb;
Var Ini : TIniFile; ProjectPath, JobPath, Medium : String; AddJob, AllowUnsaved : Boolean;
    Project : IProject; Doc : IServerDocument;
Begin
  Try
    If FileExists(StatusFile) Then DeleteFile(StatusFile);
    Log('start');
    Ini := TIniFile.Create(ConfigFile);
    Try
        ProjectPath := Ini.ReadString('Export', 'Project', '');
        AddJob := Ini.ReadString('Export', 'AddOutJob', '0') = '1';
        AllowUnsaved := Ini.ReadString('Export', 'AllowUnsaved', '0') = '1';
    Finally
        Ini.Free;
    End;
    If (ProjectPath = '') Or Not FileExists(ProjectPath) Then
    Begin Log('error: project_not_found ' + ProjectPath); Exit; End;

    Project := FindProject(ProjectPath);
    If Project = Nil Then
    Begin
        ResetParameters;
        AddStringParameter('ObjectKind', 'Project');
        AddStringParameter('FileName', ProjectPath);
        RunProcess('WorkspaceManager:OpenObject');
        Project := FindProject(ProjectPath);
    End;
    If Project = Nil Then Begin Log('error: project_not_open ' + ProjectPath); Exit; End;
    Log('project: ' + Project.DM_ProjectFullPath);
    If (UnsavedDocuments(Project) > 0) And Not AllowUnsaved Then
    Begin Log('error: unsaved_documents'); Exit; End;

    JobPath := ProjectOdbJob(Project);
    If JobPath <> '' Then Log('outjob: existing ' + JobPath)
    Else If AddJob Then
    Begin
        JobPath := AddHefexJob(Project);
        Log('outjob: added ' + JobPath);
    End
    Else Begin Log('error: no_odb_outjob'); Exit; End;

    Medium := OdbMedium(JobPath);
    Log('medium: ' + Medium);
    If Client.IsDocumentOpen(JobPath) Then Doc := Client.GetDocumentByPath(JobPath)
    Else Doc := Client.OpenDocument('OUTPUTJOB', JobPath);
    If Doc = Nil Then Begin Log('error: outjob_not_opened ' + JobPath); Exit; End;
    Client.ShowDocument(Doc);
    ResetParameters;
    AddStringParameter('Action', 'Run');
    AddStringParameter('OutputMedium', Medium);
    AddStringParameter('ObjectKind', 'OutputBatch');
    RunProcess('WorkspaceManager:GenerateReport');
    Log('output_folder: ' + ExtractFilePath(Project.DM_ProjectFullPath));
    Log('done');
  Except
    Log('error: exception');
  End;
End;
