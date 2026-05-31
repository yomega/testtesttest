// This file contains your Data Connector logic
[Version = "1.0.0"]
section PdfSpecBootstrap;

[DataSource.Kind="PdfSpecBootstrap", Publish="PdfSpecBootstrap.Publish"]
shared PdfSpecBootstrap.Contents = (optional message as text) =>
    let
        _message = if (message <> null) then message else "(no message)",
        a = "Hello from PdfSpecBootstrap: " & _message
    in
        a;

// Data Source Kind description
PdfSpecBootstrap = [
    Authentication = [
        // Key = [],
        // UsernamePassword = [],
        // Windows = [],
        Anonymous = []
    ]
];

// Data Source UI publishing description
PdfSpecBootstrap.Publish = [
    Beta = true,
    Category = "Other",
    ButtonText = { Extension.LoadString("ButtonTitle"), Extension.LoadString("ButtonHelp") },
    LearnMoreUrl = "https://powerbi.microsoft.com/",
    SourceImage = PdfSpecBootstrap.Icons,
    SourceTypeImage = PdfSpecBootstrap.Icons
];

PdfSpecBootstrap.Icons = [
    Icon16 = { Extension.Contents("PdfSpecBootstrap16.png"), Extension.Contents("PdfSpecBootstrap20.png"), Extension.Contents("PdfSpecBootstrap24.png"), Extension.Contents("PdfSpecBootstrap32.png") },
    Icon32 = { Extension.Contents("PdfSpecBootstrap32.png"), Extension.Contents("PdfSpecBootstrap40.png"), Extension.Contents("PdfSpecBootstrap48.png"), Extension.Contents("PdfSpecBootstrap64.png") }
];
