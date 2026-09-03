using Avacom.Student.ViewModels;

namespace Avacom.Student.Pages;

public partial class ResumenPage : ContentPage
{
    private readonly ResumenViewModel _viewModel;

    public ResumenPage(ResumenViewModel viewModel)
    {
        InitializeComponent();
        BindingContext = _viewModel = viewModel;
    }

    /// <summary>
    /// Cada vez que la pantalla aparece se vuelve a preguntar. El docente puede
    /// retirar material mientras la tableta está abierta, así que mostrar lo de
    /// la última vez sería enseñar algo que ya no se puede abrir.
    /// </summary>
    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _viewModel.InitializeAsync();
    }
}
