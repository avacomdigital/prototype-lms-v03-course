using Avacom.Student.PlatformServices;
using Avacom.Student.ViewModels;

namespace Avacom.Student.Pages;

public partial class ExamPage : ContentPage
{
    private readonly ExamViewModel _viewModel;
    private readonly IKioskService _kiosk;
    private readonly IEmergencyRecoveryService _recovery;
    private int _recoveryTaps;
    private DateTimeOffset _lastTap;

    public ExamPage(ExamViewModel viewModel, IKioskService kiosk, IEmergencyRecoveryService recovery)
    {
        InitializeComponent();
        BindingContext = _viewModel = viewModel;
        _kiosk = kiosk;
        _recovery = recovery;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _viewModel.InitializeAsync();
        await _kiosk.StartExamLockAsync();
    }

    protected override async void OnDisappearing()
    {
        base.OnDisappearing();
        await _kiosk.StopExamLockAsync();
        await _viewModel.DisposeAsync();
    }

    private async void OnRecoveryTap(object? sender, TappedEventArgs e)
    {
        var now = DateTimeOffset.UtcNow;
        _recoveryTaps = now - _lastTap < TimeSpan.FromSeconds(2) ? _recoveryTaps + 1 : 1;
        _lastTap = now;
        if (_recoveryTaps < 7) return;
        _recoveryTaps = 0;
        var pin = await DisplayPromptAsync("Recuperación administrativa", "Ingresa el PIN local para salir del modo restringido.", keyboard: Keyboard.Numeric);
        if (pin is not null && _recovery.ValidatePin(pin))
        {
            await _kiosk.StopExamLockAsync();
            await DisplayAlert("Modo de recuperación", "La restricción de la aplicación fue desactivada.", "Aceptar");
        }
        else if (pin is not null) await DisplayAlert("PIN incorrecto", "No se realizaron cambios.", "Aceptar");
    }
}
