using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Avacom.OPS.Master;

/// <summary>
/// Base mínima de notificación para los bloques del formulario de creación. El
/// DashboardViewModel implementa lo suyo aparte; aquí hacen falta muchas instancias
/// pequeñas y vivas, porque el docente añade y quita bloques en pantalla.
/// </summary>
public abstract class DraftFormBase : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;

    protected bool Set<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        Notify(name);
        return true;
    }

    protected void Notify([CallerMemberName] string? name = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}

/// <summary>Una lección que el docente está redactando dentro de una sección.</summary>
public sealed class LessonDraftForm : DraftFormBase
{
    private readonly Action<LessonDraftForm> _onRemove;
    private string _title = "";
    private string _description = "";
    private string _competency = "";
    private string _learningOutcome = "";
    private string _competencyLabel = "Elemento de competencia";
    private string _competencyHint = "Código del marco de referencia";
    private int _position = 1;
    private bool _canRemove = true;

    public LessonDraftForm(Action<LessonDraftForm> onRemove)
    {
        _onRemove = onRemove;
        RemoveCommand = new Command(() => _onRemove(this), () => CanRemove);
    }

    public Command RemoveCommand { get; }

    public string Title { get => _title; set { if (Set(ref _title, value)) Notify(nameof(HeaderText)); } }
    public string Description { get => _description; set => Set(ref _description, value); }
    public string LearningOutcome { get => _learningOutcome; set => Set(ref _learningOutcome, value); }

    /// <summary>Va al campo <c>competency_framework</c>. CharField(64) en el modelo.</summary>
    public string Competency { get => _competency; set => Set(ref _competency, value); }

    /// <summary>Rótulo que impone el marco curricular elegido: DBA, PDA, Competencia…</summary>
    public string CompetencyLabel { get => _competencyLabel; set => Set(ref _competencyLabel, value); }
    public string CompetencyHint { get => _competencyHint; set => Set(ref _competencyHint, value); }

    public int Position
    {
        get => _position;
        set { if (Set(ref _position, value)) { Notify(nameof(PositionLabel)); Notify(nameof(HeaderText)); } }
    }

    public string PositionLabel => $"LECCIÓN {Position:00}";

    public string HeaderText => string.IsNullOrWhiteSpace(Title)
        ? $"Lección {Position:00} · sin título"
        : $"Lección {Position:00} · {Title.Trim()}";

    public bool CanRemove
    {
        get => _canRemove;
        set { if (Set(ref _canRemove, value)) RemoveCommand.ChangeCanExecute(); }
    }

    public bool IsValid => !string.IsNullOrWhiteSpace(Title);
}

/// <summary>Una sección que el docente está armando, con sus lecciones.</summary>
public sealed class SectionDraftForm : DraftFormBase
{
    private readonly Action<SectionDraftForm> _onRemove;
    private string _title = "";
    private int _position = 1;
    private bool _canRemove = true;
    private string _competencyLabel = "Elemento de competencia";
    private string _competencyHint = "Código del marco de referencia";

    public SectionDraftForm(Action<SectionDraftForm> onRemove)
    {
        _onRemove = onRemove;
        RemoveCommand = new Command(() => _onRemove(this), () => CanRemove);
        AddLessonCommand = new Command(() => AddLesson());
    }

    public ObservableCollection<LessonDraftForm> Lessons { get; } = [];
    public Command RemoveCommand { get; }
    public Command AddLessonCommand { get; }

    public string Title { get => _title; set { if (Set(ref _title, value)) Notify(nameof(HeaderText)); } }

    public int Position
    {
        get => _position;
        set { if (Set(ref _position, value)) { Notify(nameof(PositionLabel)); Notify(nameof(HeaderText)); } }
    }

    public string PositionLabel => $"SECCIÓN {Position:00}";

    public string HeaderText => string.IsNullOrWhiteSpace(Title)
        ? $"Sección {Position:00} · sin título"
        : $"Sección {Position:00} · {Title.Trim()}";

    public string LessonCountLabel => Lessons.Count == 1 ? "1 lección" : $"{Lessons.Count} lecciones";

    public bool CanRemove
    {
        get => _canRemove;
        set { if (Set(ref _canRemove, value)) RemoveCommand.ChangeCanExecute(); }
    }

    /// <summary>El rótulo del marco baja a cada lección nueva que se cree en esta sección.</summary>
    public string CompetencyLabel
    {
        get => _competencyLabel;
        set
        {
            if (!Set(ref _competencyLabel, value)) return;
            foreach (var lesson in Lessons) lesson.CompetencyLabel = value;
        }
    }

    public string CompetencyHint
    {
        get => _competencyHint;
        set
        {
            if (!Set(ref _competencyHint, value)) return;
            foreach (var lesson in Lessons) lesson.CompetencyHint = value;
        }
    }

    public LessonDraftForm AddLesson(string title = "")
    {
        var lesson = new LessonDraftForm(RemoveLesson)
        {
            Title = title,
            CompetencyLabel = CompetencyLabel,
            CompetencyHint = CompetencyHint,
        };
        Lessons.Add(lesson);
        RenumberLessons();
        return lesson;
    }

    private void RemoveLesson(LessonDraftForm lesson)
    {
        // Una sección sin lecciones no es navegable para el estudiante: la última no se quita.
        if (Lessons.Count <= 1) return;
        Lessons.Remove(lesson);
        RenumberLessons();
    }

    private void RenumberLessons()
    {
        for (var i = 0; i < Lessons.Count; i++)
        {
            Lessons[i].Position = i + 1;
            Lessons[i].CanRemove = Lessons.Count > 1;
        }
        Notify(nameof(LessonCountLabel));
    }

    public bool IsValid => !string.IsNullOrWhiteSpace(Title) && Lessons.Count > 0 && Lessons.All(l => l.IsValid);
}
