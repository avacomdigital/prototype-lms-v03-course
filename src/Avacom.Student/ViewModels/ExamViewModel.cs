using System.Collections.ObjectModel;
using Avacom.OPS.Core.Models;
using Avacom.OPS.Core.Services;
using Avacom.Student.Pages;
using Avacom.Student.Services;

namespace Avacom.Student.ViewModels;

public sealed class ExamViewModel : ViewModelBase, IAsyncDisposable
{
    private readonly ExamSession _session;
    private readonly ILmsApiClient _api;
    private readonly ILmsRealtimeClient _realtime;
    private readonly ClientEndpointSettings _endpoint;
    private readonly ILocalLog _log;
    private readonly Dictionary<string, string> _selections = [];
    private CancellationTokenSource? _realtimeCts;
    private int _index;
    private bool _isBusy;
    private string _status = "Selecciona una respuesta.";
    private bool _initialized;

    public ExamViewModel(ExamSession session, ILmsApiClient api, ILmsRealtimeClient realtime, ClientEndpointSettings endpoint, ILocalLog log)
    {
        _session = session;
        _api = api;
        _realtime = realtime;
        _endpoint = endpoint;
        _log = log;
        SelectOptionCommand = new Command<AnswerOptionViewModel>(async option => await SelectOptionAsync(option), _ => !IsBusy);
        PreviousCommand = new Command(Previous, () => Index > 0 && !IsBusy);
        NextCommand = new Command(async () => await NextAsync(), () => !IsBusy);
        ExitCommand = new Command(async () => await Shell.Current.GoToAsync(".."));
    }

    public ObservableCollection<AnswerOptionViewModel> Options { get; } = [];
    public CourseActivity? Activity => _session.Activity;
    public string ActivityTitle => Activity?.Title ?? "Quiz";
    public string StudentName => _session.StudentName;
    public QuizQuestion? CurrentQuestion => Activity?.Questions.ElementAtOrDefault(Index);
    public string Category => CurrentQuestion?.Category.ToUpperInvariant() ?? "PREGUNTA";
    public string ProgressLabel => Activity is null ? "" : $"Pregunta {Index + 1} de {Activity.Questions.Count}";
    public double ProgressValue => Activity?.Questions.Count > 0 ? (double)(Index + 1) / Activity.Questions.Count : 0;
    public string AnsweredLabel => Activity is null ? "" : $"{_selections.Count} de {Activity.Questions.Count} respondidas";
    public string NextLabel => Activity is not null && Index == Activity.Questions.Count - 1 ? "Finalizar quiz" : "Siguiente";
    public string Status { get => _status; private set => Set(ref _status, value); }
    public bool IsBusy { get => _isBusy; private set { Set(ref _isBusy, value); RefreshCommands(); } }
    public int Index { get => _index; private set { if (Set(ref _index, value)) RefreshQuestion(); } }
    public Command<AnswerOptionViewModel> SelectOptionCommand { get; }
    public Command PreviousCommand { get; }
    public Command NextCommand { get; }
    public Command ExitCommand { get; }

    public async Task InitializeAsync()
    {
        if (_initialized || Activity is null) return;
        _initialized = true;
        IsBusy = true;
        try
        {
            var deviceId = Preferences.Default.Get("student_device_id", "");
            if (string.IsNullOrWhiteSpace(deviceId))
            {
                deviceId = $"{DeviceInfo.Current.Platform}-{Guid.NewGuid():N}";
                Preferences.Default.Set("student_device_id", deviceId);
            }
            _session.Attempt = await _api.StartQuizAsync(Activity.Id, _session.StudentName, _session.PersonId, deviceId);
            _session.IsExamInProgress = true;
            _realtimeCts = new CancellationTokenSource();
            _realtime.ConnectionChanged += OnConnectionChanged;
            _ = _realtime.RunAsync(
                _endpoint.Current.WebSocketForActivity(Activity.Id, "student", _session.Attempt.Id),
                _realtimeCts.Token);
            Index = Math.Clamp(_session.Attempt.CurrentQuestion - 1, 0, Activity.Questions.Count - 1);
            RefreshQuestion();
            await _api.ReportProgressAsync(_session.Attempt.Id, Index + 1);
        }
        catch (Exception exception)
        {
            Status = $"No se pudo iniciar: {exception.Message}";
            await _log.WriteAsync("quiz", "start_failed", exception);
        }
        finally { IsBusy = false; }
    }

    private async Task SelectOptionAsync(AnswerOptionViewModel? option)
    {
        if (option is null || CurrentQuestion is null || _session.Attempt is null) return;
        foreach (var item in Options) item.IsSelected = item.Id == option.Id;
        _selections[CurrentQuestion.Id] = option.Id;
        Notify(nameof(AnsweredLabel));
        Status = "Respuesta guardada";
        try
        {
            await _api.SaveAnswerAsync(QuizAnswerCommand.Create(_session.Attempt.Id, CurrentQuestion.Id, option.Id));
        }
        catch (Exception exception)
        {
            Status = "Sincronización pendiente; vuelve a tocar la respuesta cuando recupere la red.";
            await _log.WriteAsync("quiz", "answer_failed", exception);
        }
    }

    private async Task NextAsync()
    {
        if (Activity is null || CurrentQuestion is null || _session.Attempt is null) return;
        if (!_selections.ContainsKey(CurrentQuestion.Id))
        {
            Status = "Selecciona una opción antes de continuar.";
            return;
        }
        if (Index < Activity.Questions.Count - 1)
        {
            Index++;
            await _api.ReportProgressAsync(_session.Attempt.Id, Index + 1);
            return;
        }

        IsBusy = true;
        try
        {
            _session.Result = await _api.FinishQuizAsync(_session.Attempt.Id);
            _session.IsExamInProgress = false;
            await Shell.Current.GoToAsync(nameof(FinishedPage));
        }
        catch (Exception exception)
        {
            Status = $"No se pudo finalizar: {exception.Message}";
            await _log.WriteAsync("quiz", "finish_failed", exception);
        }
        finally { IsBusy = false; }
    }

    private void Previous()
    {
        if (Index > 0) Index--;
    }

    private void RefreshQuestion()
    {
        Options.Clear();
        if (CurrentQuestion is not null)
        {
            _selections.TryGetValue(CurrentQuestion.Id, out var selected);
            foreach (var option in CurrentQuestion.Options)
                Options.Add(new AnswerOptionViewModel(option) { IsSelected = option.Id == selected });
        }
        Notify(nameof(CurrentQuestion));
        Notify(nameof(Category));
        Notify(nameof(ProgressLabel));
        Notify(nameof(ProgressValue));
        Notify(nameof(AnsweredLabel));
        Notify(nameof(NextLabel));
        PreviousCommand.ChangeCanExecute();
    }

    private void RefreshCommands()
    {
        SelectOptionCommand.ChangeCanExecute();
        PreviousCommand.ChangeCanExecute();
        NextCommand.ChangeCanExecute();
    }

    private void OnConnectionChanged(object? sender, bool connected) => MainThread.BeginInvokeOnMainThread(() =>
        Status = connected ? "LIVE · el profesor ve tu avance" : "Reconectando el avance en vivo…");

    public async ValueTask DisposeAsync()
    {
        _realtimeCts?.Cancel();
        _realtime.ConnectionChanged -= OnConnectionChanged;
        await _realtime.DisposeAsync();
        _realtimeCts?.Dispose();
        _realtimeCts = null;
        _session.IsExamInProgress = false;
        _initialized = false;
    }
}
