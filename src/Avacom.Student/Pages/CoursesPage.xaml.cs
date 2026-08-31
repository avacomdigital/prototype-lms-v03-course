using Avacom.Student.ViewModels;

namespace Avacom.Student.Pages;

public partial class CoursesPage : ContentPage
{
    private readonly CoursesViewModel _viewModel;
    public CoursesPage(CoursesViewModel viewModel)
    {
        InitializeComponent();
        BindingContext = _viewModel = viewModel;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _viewModel.InitializeAsync();
    }
}
