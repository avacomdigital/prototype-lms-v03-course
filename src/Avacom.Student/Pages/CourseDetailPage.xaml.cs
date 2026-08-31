using Avacom.Student.ViewModels;

namespace Avacom.Student.Pages;

public partial class CourseDetailPage : ContentPage
{
    private readonly CourseDetailViewModel _viewModel;
    public CourseDetailPage(CourseDetailViewModel viewModel)
    {
        InitializeComponent();
        BindingContext = _viewModel = viewModel;
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        _viewModel.Initialize();
    }
}
