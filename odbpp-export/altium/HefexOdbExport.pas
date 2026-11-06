// Hefex Labs: export ODB++ from an Altium Designer PCB project.
//
// Runs inside the open Altium instance, started by run.ps1 (or by the agent) with
//   X2.EXE -RScriptingSystem:RunScript(ProjectName="<Kit>\HefexScripts.PrjScr"|ProcName="HefexOdbExport.pas>ExportOdb")
// Reads <Kit>\export.ini, writes every step to <Kit>\export_status.txt.
//
// export.ini:
//   [Export]
//   Project=C:\path\Board.PrjPcb   ; required
//   Action=Export                  ; Export (default) or ListVariants
//   Variant=                       ; assembly variant to export, by its name
//                                  ; (the Description in Altium); empty = none
//   AddOutJob=0                    ; 1 = the customer agreed to add Hefex.OutJob
//   AllowUnsaved=0                 ; 1 = export even with unsaved documents
//
// ListVariants logs one "variant: <name> | not_fitted: <designators> |
// alternate: <designators>" line per variant and exports nothing.
//
// Unsaved project documents stop the export (error: unsaved_documents, each
// one listed as "unsaved: <path>"), so nobody orders a state they did not save,
// unless AllowUnsaved=1.
//
// Output job: without a variant, an ODB++ output job that is already part of
// the project is used as it is (its own variant setting is logged as
// "outjob_variant:"). With a variant, an existing job is only used when its ODB
// output already exports that variant; otherwise Hefex.OutJob is used, because
// the script never changes the customer's own output jobs. Hefex.OutJob is
// copied next to the project, added and the project saved only when AddOutJob=1.
// The script sets the variant in Hefex.OutJob before each run.
//
// Every step is inside Try/Except. That catches runtime errors only: an unknown
// identifier or a file that cannot be opened shows a modal error dialog and
// leaves the script paused in the debugger; Altium then refuses every later
// script until "Stop Debugging" (X2.EXE -REditScript:Stop). The status file is
// opened and closed for every line so that a stopped run never keeps it locked.

Const
    Kit        = 'C:\Users\Public\Documents\Hefex\altium\';
    StatusFile = 'C:\Users\Public\Documents\Hefex\altium\export_status.txt';
    ConfigFile = 'C:\Users\Public\Documents\Hefex\altium\export.ini';
    Template   = 'C:\Users\Public\Documents\Hefex\altium\Hefex.OutJob';
    NoVariant  = '[No Variations]';
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

// The variant of the project whose name (Description in Altium) is Name, Nil when none.
Function FindVariant(Project : IProject; Name : String) : IProjectVariant;
Var I : Integer; V : IProjectVariant;
Begin
    Result := Nil;
    For I := 0 To Project.DM_ProjectVariantCount - 1 Do
    Begin
        V := Project.DM_ProjectVariants(I);
        If LowerCase(Trim(V.DM_Description)) = LowerCase(Trim(Name)) Then Result := V;
    End;
End;

// Designators of the variant's components with the given variation kind, comma separated.
Function Variations(V : IProjectVariant; Kind : Integer) : String;
Var I : Integer; CV : IComponentVariation;
Begin
    Result := '';
    For I := 0 To V.DM_VariationCount - 1 Do
    Begin
        CV := V.DM_Variations(I);
        If CV.DM_VariationKind = Kind Then
        Begin
            If Result <> '' Then Result := Result + ',';
            Result := Result + CV.DM_PhysicalDesignator;
        End;
    End;
End;

Procedure LogVariants(Project : IProject);
Var I : Integer; V : IProjectVariant;
Begin
    Log('variants: ' + IntToStr(Project.DM_ProjectVariantCount));
    For I := 0 To Project.DM_ProjectVariantCount - 1 Do
    Begin
        V := Project.DM_ProjectVariants(I);
        Log('variant: ' + V.DM_Description
            + ' | not_fitted: ' + Variations(V, eVariation_NotFitted)
            + ' | alternate: ' + Variations(V, eVariation_Alternate));
    End;
End;

// The first medium of a GeneratedFiles type that an ODB output of the job is
// enabled for, '' when the job has no such output. OdbVariant is set to the
// variant that output exports ('[No Variations]' when none).
Function OdbOutput(OutJobPath : String; Var OdbVariant : String) : String;
Var Ini : TIniFile; G, K, J : Integer; Section, Medium, V : String;
Begin
    Result := '';
    OdbVariant := NoVariant;
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
                        Begin
                            Result := Medium;
                            // VariantScope=1: every output has its own variant.
                            If Ini.ReadString(Section, 'VariantScope', '0') = '1' Then
                                V := Ini.ReadString(Section, 'OutputVariantName' + IntToStr(K), '')
                            Else
                                V := Ini.ReadString(Section, 'VariantName', '');
                            If V <> '' Then OdbVariant := V;
                        End;
                    End;
            End;
        End;
    Finally
        Ini.Free;
    End;
End;

// An output job of the project with an enabled ODB output, '' when none.
// With Wanted <> '', only a job whose ODB output exports that variant counts.
Function ProjectOdbJob(Project : IProject; Wanted : String) : String;
Var I : Integer; Path, V : String;
Begin
    Result := '';
    For I := 0 To Project.DM_LogicalDocumentCount - 1 Do
    Begin
        Path := Project.DM_LogicalDocuments(I).DM_FullPath;
        If (Result = '') And (LowerCase(ExtractFileExt(Path)) = '.outjob')
            And (LowerCase(ExtractFileName(Path)) <> 'hefex.outjob')
            And (OdbOutput(Path, V) <> '') Then
            If (Wanted = '') Or (LowerCase(V) = LowerCase(Wanted)) Then
                Result := Path;
    End;
End;

// Hefex.OutJob next to the project when it is part of the project, '' otherwise.
Function ProjectHefexJob(Project : IProject) : String;
Var I : Integer; Path : String;
Begin
    Result := '';
    For I := 0 To Project.DM_LogicalDocumentCount - 1 Do
    Begin
        Path := Project.DM_LogicalDocuments(I).DM_FullPath;
        If LowerCase(ExtractFileName(Path)) = 'hefex.outjob' Then Result := Path;
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

// Writes the variant into Hefex.OutJob. The job must not be open while its file
// changes, so it is closed first (it was checked to be saved). False on failure.
// The ODB++ settings come from the template: an output without them exports no
// copper layers, and without IncludeVariantsData it ignores the variant. Copying
// them every run also updates a Hefex.OutJob added by an older kit.
Function SetJobVariant(JobPath, Variant : String) : Boolean;
Var Ini : TIniFile; Tpl : TStringList; Doc : IServerDocument; Cfg : String; I : Integer;
Begin
    Result := False;
    If Client.IsDocumentOpen(JobPath) Then
    Begin
        Doc := Client.GetDocumentByPath(JobPath);
        If (Doc <> Nil) And Doc.Modified Then Begin Log('error: outjob_unsaved ' + JobPath); Exit; End;
        If Doc <> Nil Then Client.CloseDocument(Doc);
    End;
    // Read as text: TIniFile.ReadString cuts values after 2047 characters.
    Cfg := '';
    Tpl := TStringList.Create;
    Try
        Tpl.LoadFromFile(Template);
        For I := 0 To Tpl.Count - 1 Do
            If Pos('Configuration1_Item1=', Tpl[I]) = 1 Then
                Cfg := Copy(Tpl[I], Length('Configuration1_Item1=') + 1, Length(Tpl[I]));
    Finally
        Tpl.Free;
    End;
    If Cfg = '' Then Begin Log('error: template_without_odb_settings ' + Template); Exit; End;
    Ini := TIniFile.Create(JobPath);
    Try
        Ini.WriteString('OutputGroup1', 'VariantName', Variant);
        Ini.WriteString('OutputGroup1', 'VariantScope', '0');
        Ini.WriteString('OutputGroup1', 'Configuration1_Name1', 'OutputConfigurationParameter1');
        Ini.WriteString('OutputGroup1', 'Configuration1_Item1', Cfg);
    Finally
        Ini.Free;
    End;
    Result := True;
End;

Procedure ExportOdb;
Var Ini : TIniFile; ProjectPath, JobPath, Medium, Action, Variant, JobVariant : String;
    AddJob, AllowUnsaved : Boolean; Project : IProject; Doc : IServerDocument;
Begin
  Try
    If FileExists(StatusFile) Then DeleteFile(StatusFile);
    Log('start');
    Ini := TIniFile.Create(ConfigFile);
    Try
        ProjectPath := Ini.ReadString('Export', 'Project', '');
        Action := LowerCase(Ini.ReadString('Export', 'Action', 'Export'));
        Variant := Trim(Ini.ReadString('Export', 'Variant', ''));
        AddJob := Ini.ReadString('Export', 'AddOutJob', '0') = '1';
        AllowUnsaved := Ini.ReadString('Export', 'AllowUnsaved', '0') = '1';
    Finally
        Ini.Free;
    End;
    If LowerCase(Variant) = LowerCase(NoVariant) Then Variant := '';
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

    If Action = 'listvariants' Then
    Begin
        LogVariants(Project);
        Log('done');
        Exit;
    End;

    If (UnsavedDocuments(Project) > 0) And Not AllowUnsaved Then
    Begin Log('error: unsaved_documents'); Exit; End;

    If Variant <> '' Then
    Begin
        If FindVariant(Project, Variant) = Nil Then
        Begin
            LogVariants(Project);
            Log('error: variant_not_found ' + Variant);
            Exit;
        End;
        Log('variant: ' + Variant);
    End
    Else If Project.DM_ProjectVariantCount > 0 Then
        Log('warning: project_has_variants ' + IntToStr(Project.DM_ProjectVariantCount) + ', exporting without one');

    // An own job that already exports the wanted state, else Hefex.OutJob.
    If Variant = '' Then JobPath := ProjectOdbJob(Project, '')
    Else JobPath := ProjectOdbJob(Project, Variant);
    If JobPath <> '' Then Log('outjob: existing ' + JobPath)
    Else
    Begin
        JobPath := ProjectHefexJob(Project);
        If JobPath <> '' Then Log('outjob: hefex ' + JobPath)
        Else If AddJob Then
        Begin
            JobPath := AddHefexJob(Project);
            Log('outjob: added ' + JobPath);
        End
        Else
        Begin
            If Variant <> '' Then Log('error: no_odb_outjob_for_variant ' + Variant)
            Else Log('error: no_odb_outjob');
            Exit;
        End;
        If Variant = '' Then
        Begin
            If Not SetJobVariant(JobPath, NoVariant) Then Exit;
        End
        Else If Not SetJobVariant(JobPath, Variant) Then Exit;
    End;

    Medium := OdbOutput(JobPath, JobVariant);
    Log('medium: ' + Medium);
    Log('outjob_variant: ' + JobVariant);
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
