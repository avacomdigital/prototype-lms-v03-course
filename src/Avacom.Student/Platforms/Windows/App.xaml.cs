namespace Avacom.Student.WinUI;

public partial class App : MauiWinUIApplication
{
    public App() => InitializeComponent();

    protected override MauiApp CreateMauiApp()
    {
        // En un equipo en modo kiosco no hay consola ni ventana donde ver un fallo de
        // arranque: Windows sólo deja un 0x80131604 sin la excepción interna. Esta
        // traza es la única forma de diagnosticarlo en la sede.
        try
        {
            return MauiProgram.CreateMauiApp();
        }
        catch (Exception exception)
        {
            try
            {
                File.AppendAllText(
                    Path.Combine(Path.GetTempPath(), "avacom-student-startup.log"),
                    $"{DateTimeOffset.Now:O} arranque fallido{Environment.NewLine}{exception}{Environment.NewLine}{Environment.NewLine}");
            }
            catch
            {
                // Si no se puede escribir la traza no hay nada más que hacer.
            }
            throw;
        }
    }
}
