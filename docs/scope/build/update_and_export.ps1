# Opens the generated scope document in Microsoft Word, updates every field (SEQ caption numbers,
# table of contents, list of figures, list of tables, page numbers), saves it, and
# exports a PDF next to it. Run after build_scope.py.
# Word works on a copy in %TEMP% because saving straight into the OneDrive folder can
# stall while OneDrive holds the file; the results are copied back at the end.
$ErrorActionPreference = "Stop"
$srs  = Split-Path -Parent $PSScriptRoot
$docx = Join-Path $srs "Scope_Document_v3.1.docx"
$pdf  = Join-Path $srs "Scope_Document_v3.1.pdf"
$tdoc = Join-Path $env:TEMP "scope_work.docx"
$tpdf = Join-Path $env:TEMP "scope_work.pdf"
Copy-Item $docx $tdoc -Force

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($tdoc, $false, $false, $false)
    # Word re-creates its built-in TOC styles when it builds a TOC, so set the
    # department formatting on them here: Times New Roman, left aligned, chapter lines bold.
    foreach ($n in "TOC 1", "TOC 2", "TOC 3", "Table of Figures") {
        $st = $doc.Styles.Item($n)
        $st.Font.Name = "Times New Roman"
        $st.Font.Size = 12
        $st.ParagraphFormat.Alignment = 0              # wdAlignParagraphLeft
        $st.ParagraphFormat.RightIndent = 28.8        # 0.4 in, keeps text clear of page numbers
    }
    $doc.Styles.Item("TOC 1").Font.Bold = $true
    $doc.Styles.Item("TOC 1").ParagraphFormat.SpaceBefore = 4
    $doc.Styles.Item("TOC 2").ParagraphFormat.LeftIndent = 18
    $doc.Styles.Item("TOC 3").ParagraphFormat.LeftIndent = 36
    $tof = $doc.Styles.Item("Table of Figures").ParagraphFormat
    $tof.LeftIndent = 68.4; $tof.FirstLineIndent = -68.4   # hanging indent under "Table 2.10:"
    $doc.Fields.Update() | Out-Null                 # caption SEQ numbers first
    "fields updated"
    foreach ($t in $doc.TablesOfContents) { $t.Update() | Out-Null }
    "TOC updated"
    foreach ($t in $doc.TablesOfFigures)  { $t.Update() | Out-Null }
    "lists of figures/tables updated"
    $doc.Repaginate()
    foreach ($t in $doc.TablesOfContents) { $t.UpdatePageNumbers() | Out-Null }
    foreach ($t in $doc.TablesOfFigures)  { $t.UpdatePageNumbers() | Out-Null }
    "page numbers refreshed"
    $doc.Save()
    "saved"
    "pages: " + $doc.ComputeStatistics(2)
    # SaveAs2 with wdFormatPDF (17); ExportAsFixedFormat stalls on this machine.
    [string]$pdfPath = $tpdf
    $doc.SaveAs2($pdfPath, 17)
    "pdf written"
    $doc.Close(0)
} finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
Copy-Item $tdoc $docx -Force
Copy-Item $tpdf $pdf -Force
"saved $docx"
"exported $pdf"

