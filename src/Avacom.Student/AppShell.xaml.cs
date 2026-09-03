using Avacom.Student.Pages;

namespace Avacom.Student;

public partial class AppShell : Shell
{
    public AppShell(RegistrationPage registrationPage)
    {
        InitializeComponent();
        RootContent.Content = registrationPage;
        // Dos pantallas y nada más: entrar, y ver qué hay. Todo lo demás que
        // había aquí —detalle, examen, resultado— se quitó.
        Routing.RegisterRoute(nameof(ResumenPage), typeof(ResumenPage));
    }
}
