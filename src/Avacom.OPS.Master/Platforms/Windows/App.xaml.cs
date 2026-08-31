namespace Avacom.OPS.Master.WinUI;

public partial class App : MauiWinUIApplication
{
    public App() => InitializeComponent();

    protected override MauiApp CreateMauiApp()
    {
        // Un fallo aquí cierra la aplicación antes de que exista una ventana donde
        // mostrarlo: Windows sólo registra un 0x80131604 sin la excepción interna.
        // Dejar traza en disco es la única forma de diagnosticarlo en la sede.
        try
        {
            return MauiProgram.CreateMauiApp();
        }
        catch (Exception exception)
        {
            WriteStartupFailure(exception);
            throw;
        }
    }

    private static void WriteStartupFailure(Exception exception)
    {
        try
        {
            var path = Path.Combine(Path.GetTempPath(), "avacom-master-startup.log");
            File.AppendAllText(path,
                $"{DateTimeOffset.Now:O} arranque fallido{Environment.NewLine}{exception}{Environment.NewLine}{Environment.NewLine}");
        }
        catch
        {
            // Si no se puede escribir la traza no hay nada más que hacer.
        }
    }
}
