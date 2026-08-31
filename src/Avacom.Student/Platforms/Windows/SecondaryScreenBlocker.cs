using Microsoft.UI.Windowing;
using WinRT.Interop;

namespace Avacom.Student.Platforms.Windows;

/// <summary>
/// Cubre con una ventana opaca cada monitor distinto al del examen, para que no quede
/// una pantalla libre donde consultar respuestas.
/// </summary>
/// <remarks>
/// Si los monitores están en modo <b>duplicado</b>, Windows expone un solo display y
/// ambos muestran ya lo mismo: no hay nada que cubrir. Esto actúa en modo
/// <b>extendido</b>, que es el caso en el que sí se podría hacer trampa.
/// </remarks>
internal static class SecondaryScreenBlocker
{
    private static readonly List<Window> Blockers = [];

    internal static int ActiveCount => Blockers.Count;

    /// <summary>Cubre todos los monitores menos el que ocupa la ventana del examen.</summary>
    internal static void Cover()
    {
        if (Blockers.Count > 0) return;

        var examWindow = Application.Current?.Windows.FirstOrDefault();
        var examDisplay = DisplayAreaOf(examWindow);

        foreach (var display in DisplayArea.FindAll())
        {
            if (examDisplay is not null && display.DisplayId.Value == examDisplay.DisplayId.Value) continue;
            Blockers.Add(CreateBlocker(display));
        }
    }

    internal static void Uncover()
    {
        foreach (var blocker in Blockers.ToList())
        {
            try { Application.Current?.CloseWindow(blocker); }
            catch (Exception) { /* la ventana ya pudo cerrarse con la aplicación */ }
        }
        Blockers.Clear();
    }

    private static Window CreateBlocker(DisplayArea display)
    {
        var window = new Window(new ContentPage
        {
            BackgroundColor = Color.FromArgb("#0E1B22"),
            Content = new VerticalStackLayout
            {
                Spacing = 14,
                HorizontalOptions = LayoutOptions.Center,
                VerticalOptions = LayoutOptions.Center,
                Children =
                {
                    new Label
                    {
                        Text = "AVACOM · EXAMEN EN CURSO",
                        TextColor = Color.FromArgb("#6FBFC3"),
                        FontSize = 15,
                        HorizontalTextAlignment = TextAlignment.Center,
                    },
                    new Label
                    {
                        Text = "Esta pantalla queda bloqueada durante el examen.",
                        TextColor = Color.FromArgb("#E2EEF0"),
                        FontSize = 22,
                        HorizontalTextAlignment = TextAlignment.Center,
                    },
                },
            },
        })
        {
            Title = "AVACOM Student · pantalla bloqueada",
        };

        Application.Current!.OpenWindow(window);

        // La ventana nativa no existe hasta que MAUI la crea, así que se coloca en el
        // monitor de destino en cuanto está disponible.
        window.Created += (_, _) => MainThread.BeginInvokeOnMainThread(() => MoveToDisplay(window, display));
        return window;
    }

    private static void MoveToDisplay(Window window, DisplayArea display)
    {
        var appWindow = AppWindowOf(window);
        if (appWindow is null) return;

        var bounds = display.OuterBounds;
        // global:: es obligatorio: el namespace de este archivo termina en .Windows, así
        // que "Windows.Graphics" se resolvería contra él en lugar del SDK.
        appWindow.MoveAndResize(new global::Windows.Graphics.RectInt32(bounds.X, bounds.Y, bounds.Width, bounds.Height));
        appWindow.SetPresenter(AppWindowPresenterKind.FullScreen);
    }

    private static DisplayArea? DisplayAreaOf(Window? window)
    {
        var appWindow = AppWindowOf(window);
        return appWindow is null ? null : DisplayArea.GetFromWindowId(appWindow.Id, DisplayAreaFallback.Primary);
    }

    private static AppWindow? AppWindowOf(Window? window)
    {
        if (window?.Handler?.PlatformView is not Microsoft.UI.Xaml.Window native) return null;
        var id = Microsoft.UI.Win32Interop.GetWindowIdFromWindow(WindowNative.GetWindowHandle(native));
        return AppWindow.GetFromWindowId(id);
    }
}
