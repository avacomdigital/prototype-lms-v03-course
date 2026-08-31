using System.Text.Json.Serialization;

namespace Avacom.OPS.Core.Models;

public sealed record CurriculumFramework(
    [property: JsonPropertyName("clave")] string Key,
    [property: JsonPropertyName("nombre")] string Name,
    [property: JsonPropertyName("pais")] string? Country)
{
    /// <summary>
    /// Cómo llama cada sistema educativo al elemento de competencia que se registra en
    /// <c>competency_framework</c>. El docente colombiano busca un DBA y el mexicano una
    /// PDA: el campo es el mismo, el nombre en pantalla no puede serlo.
    /// Se resuelve por país y no por clave, así que una fila nueva —de EEUU, por ejemplo—
    /// queda rotulada sin tocar código.
    /// </summary>
    public string CompetencyLabel => (Country ?? "").Trim().ToUpperInvariant() switch
    {
        "CO" => "DBA",
        "MX" => "PDA",
        "ES" => "Competencia",
        "US" => "Knowledge Competency",
        _ => "Elemento de competencia",
    };

    /// <summary>Ayuda breve bajo el campo, con un ejemplo del formato que espera cada marco.</summary>
    public string CompetencyHint => (Country ?? "").Trim().ToUpperInvariant() switch
    {
        "CO" => "Derecho Básico de Aprendizaje · ej. DBA 3",
        "MX" => "Progresión de Aprendizaje · ej. PDA 2.4",
        "ES" => "Competencia específica LOMLOE · ej. CE 1.2",
        "US" => "Knowledge competency · e.g. 8.EE.C.7",
        _ => "Código del marco de referencia",
    };

    public string DisplayName => string.IsNullOrWhiteSpace(Country) ? Name : $"{Name} · {Country}";
}

public sealed record CourseEnrollment(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("persona_id")] string PersonId,
    [property: JsonPropertyName("estado")] string Status);

public sealed record LearningResource(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Title,
    [property: JsonPropertyName("content_type")] string ContentType,
    [property: JsonPropertyName("content_ref")] string ContentReference,
    [property: JsonPropertyName("content_version")] string ContentVersion,
    [property: JsonPropertyName("duracion_seg")] int? DurationSeconds)
{
    public string TypeLabel => ContentType switch
    {
        "reading" => "Lectura",
        "video" => "Video",
        "audio" => "Audio",
        _ => "Recurso",
    };
}

public sealed record QuizOption(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("texto")] string Text,
    [property: JsonPropertyName("orden")] int Position)
{
    public string Letter => Position is >= 1 and <= 26 ? ((char)('A' + Position - 1)).ToString() : Position.ToString();
}

public sealed record QuizQuestion(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("categoria")] string Category,
    [property: JsonPropertyName("texto")] string Text,
    [property: JsonPropertyName("orden")] int Position,
    [property: JsonPropertyName("opciones")] IReadOnlyList<QuizOption> Options);

public sealed record CourseActivity(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Title,
    [property: JsonPropertyName("descripcion")] string? Description,
    [property: JsonPropertyName("activity_type")] string ActivityType,
    [property: JsonPropertyName("submission_type")] string SubmissionType,
    [property: JsonPropertyName("grading_type")] string GradingType,
    [property: JsonPropertyName("max_score")] decimal MaxScore,
    [property: JsonPropertyName("estado")] string Status,
    [property: JsonPropertyName("preguntas")] IReadOnlyList<QuizQuestion> Questions)
{
    public bool IsQuiz => ActivityType == "quiz";
    public string QuestionCountLabel => $"{Questions.Count} preguntas · {MaxScore:0} puntos";
}

public sealed record LessonItem(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("orden")] int Position,
    [property: JsonPropertyName("tipo")] string Type,
    [property: JsonPropertyName("actividad")] CourseActivity? Activity,
    [property: JsonPropertyName("recurso")] LearningResource? Resource,
    [property: JsonPropertyName("elemento_ref")] string? ExternalReference,
    [property: JsonPropertyName("elemento_version")] string? ExternalVersion,
    [property: JsonPropertyName("titulo")] string Title,
    [property: JsonPropertyName("subtitulo")] string Subtitle)
{
    public bool IsQuiz => Activity?.IsQuiz == true;
    public string TypeIcon => Type switch { "actividad" => "?", "contenido" => "▤", _ => "↗" };
}

public sealed record Lesson(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Title,
    [property: JsonPropertyName("descripcion")] string? Description,
    [property: JsonPropertyName("competency_framework")] string? CompetencyFramework,
    [property: JsonPropertyName("learning_outcome")] string? LearningOutcome,
    [property: JsonPropertyName("skills")] string? Skills,
    [property: JsonPropertyName("attitudes_values")] string? AttitudesValues,
    [property: JsonPropertyName("orden")] int Position,
    [property: JsonPropertyName("estado")] string Status,
    [property: JsonPropertyName("items")] IReadOnlyList<LessonItem> Items)
{
    public string NumberLabel => $"LECCIÓN {Position:00}";
    public string ItemCountLabel => $"{Items.Count} contenidos";
}

public sealed record CourseSection(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Title,
    [property: JsonPropertyName("orden")] int Position,
    [property: JsonPropertyName("lecciones")] IReadOnlyList<Lesson> Lessons)
{
    public string NumberLabel => $"SECCIÓN {Position:00}";
    public string LessonCountLabel => $"{Lessons.Count} lecciones";
}

public sealed record Course(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("titulo")] string Title,
    [property: JsonPropertyName("descripcion")] string? Description,
    [property: JsonPropertyName("docente_id")] string TeacherId,
    [property: JsonPropertyName("curriculum_framework")] CurriculumFramework Framework,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("estado")] string Status,
    [property: JsonPropertyName("idioma")] string Language,
    [property: JsonPropertyName("secciones")] IReadOnlyList<CourseSection> Sections,
    [property: JsonPropertyName("inscripciones")] IReadOnlyList<CourseEnrollment> Enrollments,
    [property: JsonPropertyName("total_lecciones")] int TotalLessons,
    [property: JsonPropertyName("total_items")] int TotalItems)
{
    public string StatusLabel => Status switch
    {
        "habilitado" => "Publicado",
        "pruebas" => "En pruebas",
        "borrador" => "Borrador",
        _ => "Retirado",
    };

    public string Summary => $"{Sections.Count} secciones · {TotalLessons} lecciones · {TotalItems} ítems";

    [JsonIgnore]
    public CourseActivity? Quiz => Sections.SelectMany(section => section.Lessons)
        .SelectMany(lesson => lesson.Items)
        .Select(item => item.Activity)
        .FirstOrDefault(activity => activity?.IsQuiz == true);
}

public sealed record QuizAttempt(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("actividad")] string ActivityId,
    [property: JsonPropertyName("actividad_titulo")] string ActivityTitle,
    [property: JsonPropertyName("persona_id")] string PersonId,
    [property: JsonPropertyName("nombre_estudiante")] string StudentName,
    [property: JsonPropertyName("device_id")] string DeviceId,
    [property: JsonPropertyName("estado")] string Status,
    [property: JsonPropertyName("pregunta_actual")] int CurrentQuestion,
    [property: JsonPropertyName("puntaje")] decimal Score,
    [property: JsonPropertyName("total_preguntas")] int TotalQuestions,
    [property: JsonPropertyName("porcentaje")] int Percentage,
    [property: JsonPropertyName("respondidas")] int Answered,
    [property: JsonPropertyName("iniciado_en")] long StartedAt,
    [property: JsonPropertyName("finalizado_en")] long? FinishedAt)
{
    public bool IsFinished => Status == "finalizado";
    public string StatusLabel => IsFinished ? "Finalizado" : $"Pregunta {CurrentQuestion} de {TotalQuestions}";
    public string ScoreLabel => IsFinished ? $"{Score:0}/{100}" : "En curso";
    public double Progress => TotalQuestions == 0 ? 0 : Math.Clamp((double)CurrentQuestion / TotalQuestions, 0, 1);
}

public sealed record QuizAnswerResult(
    [property: JsonPropertyName("pregunta")] string Question,
    [property: JsonPropertyName("seleccionada")] string Selected,
    [property: JsonPropertyName("correcta")] string Correct,
    [property: JsonPropertyName("es_correcta")] bool IsCorrect);

public sealed record QuizResultDetail(
    [property: JsonPropertyName("summary")] QuizAttempt Summary,
    [property: JsonPropertyName("answers")] IReadOnlyList<QuizAnswerResult> Answers);

/// <summary>
/// Una lección del borrador. <paramref name="CompetencyFramework"/> viaja al campo
/// <c>competency_framework</c> de <c>m05_leccion</c>, que es un CharField(64): el
/// docente escribe el código de su marco (un DBA colombiano, una PDA mexicana, una
/// competencia LOMLOE), no un texto largo.
/// </summary>
public sealed record LessonDraft(
    string Title,
    string Description,
    string CompetencyFramework,
    string LearningOutcome);

/// <summary>Una sección del borrador con las lecciones que el docente le añadió.</summary>
public sealed record SectionDraft(
    string Title,
    IReadOnlyList<LessonDraft> Lessons);

/// <summary>
/// Borrador completo del curso. El número de secciones y de lecciones por sección lo
/// decide el docente en la OPS; el backend ya aceptaba cualquier cantidad —eran el
/// contrato y el formulario los que estaban fijos en dos secciones y tres lecciones.
/// </summary>
public sealed record CourseDraftCommand(
    string Title,
    string Description,
    string CurriculumFramework,
    IReadOnlyList<SectionDraft> Sections);

public sealed record QuizAnswerCommand(
    [property: JsonPropertyName("intento_id")] string AttemptId,
    [property: JsonPropertyName("pregunta_id")] string QuestionId,
    [property: JsonPropertyName("opcion_id")] string OptionId,
    [property: JsonPropertyName("client_event_id")] string ClientEventId)
{
    public static QuizAnswerCommand Create(string attemptId, string questionId, string optionId) =>
        new(attemptId, questionId, optionId, Guid.NewGuid().ToString("N"));
}

public sealed record LmsRealtimeEvent(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("connected_students")] int ConnectedStudents = 0,
    [property: JsonPropertyName("activity_id")] string? ActivityId = null,
    [property: JsonPropertyName("status")] string? Status = null,
    [property: JsonPropertyName("attempt")] QuizAttempt? Attempt = null);

// ═══════════════════════════════════════════════════════════════════════════
// IMPORTACIÓN DE UN PAQUETE DE CURSO
//
// El docente abre un archivo .json en la OPS. Primero se INSPECCIONA —sin
// escribir nada— para que pueda ver qué trae y confirmar; recién entonces se
// importa. Django hace la instalación en una transacción y deja el curso
// disponible para las tabletas.
// ═══════════════════════════════════════════════════════════════════════════

/// <summary>Lo que trae el paquete, leído sin tocar la base.</summary>
public sealed record CoursePackagePreview(
    [property: JsonPropertyName("course_id")] string CourseId,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("package_version")] string? PackageVersion,
    [property: JsonPropertyName("huella")] string? Fingerprint,
    [property: JsonPropertyName("notas")] string? Notes,
    [property: JsonPropertyName("activate_after_install")] bool ActivateAfterInstall,
    [property: JsonPropertyName("secciones")] int Sections,
    [property: JsonPropertyName("lecciones")] int Lessons,
    [property: JsonPropertyName("items")] int Items,
    [property: JsonPropertyName("recursos")] int Resources,
    [property: JsonPropertyName("actividades")] int Activities,
    [property: JsonPropertyName("curso_existe")] bool CourseExists,
    [property: JsonPropertyName("curso_titulo")] string? ExistingTitle,
    [property: JsonPropertyName("titulo_sugerido")] string SuggestedTitle,
    [property: JsonPropertyName("version_ya_instalada")] bool VersionAlreadyInstalled,
    [property: JsonPropertyName("misma_huella")] bool SameFingerprint)
{
    public string Summary => $"{Sections} secciones · {Lessons} lecciones · {Items} ítems";

    public string ContentSummary =>
        $"{Resources} recursos · {Activities} actividades";

    /// <summary>Qué va a pasar al confirmar, dicho en una frase.</summary>
    public string Intent => (CourseExists, VersionAlreadyInstalled, SameFingerprint) switch
    {
        (false, _, _) => $"Se creará el curso y su versión {Version}.",
        (true, true, true) => $"La versión {Version} ya está instalada. Importar de nuevo no duplica nada.",
        (true, true, false) => $"La versión {Version} ya existe con otro contenido. Usa un número de versión nuevo.",
        (true, false, _) => $"Se añadirá la versión {Version} al curso existente sin tocar las anteriores.",
    };

    public bool CanImport => !(VersionAlreadyInstalled && !SameFingerprint);

    /// <summary>Solo hace falta pedir título y marco si el curso todavía no existe.</summary>
    public bool NeedsCourseDetails => !CourseExists;
}

public sealed record ImportedVersionCounts(
    [property: JsonPropertyName("secciones")] int Sections,
    [property: JsonPropertyName("lecciones")] int Lessons,
    [property: JsonPropertyName("items")] int Items,
    [property: JsonPropertyName("recursos")] int Resources,
    [property: JsonPropertyName("actividades")] int Activities);

public sealed record VersionTotals(
    [property: JsonPropertyName("secciones")] int Sections,
    [property: JsonPropertyName("lecciones")] int Lessons,
    [property: JsonPropertyName("items")] int Items);

/// <summary>Qué quedó tras la importación.</summary>
public sealed record CoursePackageImportResult(
    [property: JsonPropertyName("course_id")] string CourseId,
    [property: JsonPropertyName("curso_titulo")] string CourseTitle,
    [property: JsonPropertyName("curso_estado")] string CourseStatus,
    [property: JsonPropertyName("curso_creado")] bool CourseCreated,
    [property: JsonPropertyName("version_id")] string VersionId,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("version_estado")] string VersionStatus,
    [property: JsonPropertyName("package_version")] string? PackageVersion,
    [property: JsonPropertyName("idempotente")] bool Idempotent,
    [property: JsonPropertyName("activada")] bool Activated,
    [property: JsonPropertyName("version_activa_id")] string? ActiveVersionId,
    [property: JsonPropertyName("creados")] ImportedVersionCounts Created,
    [property: JsonPropertyName("totales_version")] VersionTotals Totals)
{
    public bool IsAvailableToStudents =>
        CourseStatus == "habilitado" && ActiveVersionId == VersionId;

    public string Headline => Idempotent
        ? $"«{CourseTitle}» ya tenía la versión {Version} instalada."
        : CourseCreated
            ? $"«{CourseTitle}» se importó como curso nuevo, versión {Version}."
            : $"«{CourseTitle}» recibió la versión {Version}.";

    public string Detail => $"{Totals.Sections} secciones · {Totals.Lessons} lecciones · {Totals.Items} ítems";
}

/// <summary>
/// Lo que aporta quien importa, porque el paquete no lo declara: el paquete
/// trae su course_id pero no el título del curso ni su marco curricular.
/// </summary>
public sealed record CoursePackageImportOptions(
    string? Title = null,
    string? CurriculumFramework = null,
    string? TeacherId = null,
    string? Actor = null,
    bool? Activate = null);

// ═══════════════════════════════════════════════════════════════════════════
// IMPORTACIÓN DE UN PAQUETE SCORM / CMI5  (.zip)
//
// El backend detecta el formato leyendo el descriptor del .zip —imsmanifest.xml
// o cmi5.xml—, importa la estructura al mismo árbol de AVACOM y registra la
// presencia en m05_curso_host. Aquí solo viajan los tipos del cliente: el .zip
// entra como byte[] y sale un resultado tipado.
// ═══════════════════════════════════════════════════════════════════════════

public sealed record ZipPackageCounts(
    [property: JsonPropertyName("secciones")] int Sections,
    [property: JsonPropertyName("lecciones")] int Lessons,
    [property: JsonPropertyName("items")] int Items,
    [property: JsonPropertyName("recursos")] int Resources,
    [property: JsonPropertyName("actividades")] int Activities)
{
    public string Summary => $"{Sections} secciones · {Lessons} lecciones · {Items} ítems";
    public string ContentSummary => $"{Resources} recursos · {Activities} actividades";
}

/// <summary>Lo que el backend leyó del .zip, sin escribir nada en la base.</summary>
public sealed record ZipPackageDetected(
    [property: JsonPropertyName("package_name")] string PackageName,
    [property: JsonPropertyName("content_format")] string ContentFormat,
    [property: JsonPropertyName("manifest_type")] string? ManifestType,
    [property: JsonPropertyName("manifest_ref")] string? ManifestRef,
    [property: JsonPropertyName("package_identifier")] string PackageIdentifier,
    [property: JsonPropertyName("package_version")] string? PackageVersion,
    [property: JsonPropertyName("package_huella")] string? Fingerprint,
    [property: JsonPropertyName("detected_title")] string DetectedTitle,
    [property: JsonPropertyName("course_id")] string CourseId,
    [property: JsonPropertyName("course_exists")] bool CourseExists,
    [property: JsonPropertyName("existing_title")] string? ExistingTitle,
    [property: JsonPropertyName("version")] int Version,
    [property: JsonPropertyName("counts")] ZipPackageCounts Counts)
{
    /// <summary>Cómo se llama el estándar en pantalla.</summary>
    public string FormatLabel => ContentFormat switch
    {
        "scorm_12" => "SCORM 1.2",
        "scorm_2004" => "SCORM 2004",
        "cmi5" => "cmi5",
        "avacom_v1" => "Paquete AVACOM",
        _ => ContentFormat,
    };

    public string DescriptorLabel => string.IsNullOrWhiteSpace(ManifestRef)
        ? "sin descriptor"
        : $"{ManifestType}: {ManifestRef}";

    /// <summary>Solo hace falta pedir título y marco si el curso todavía no existe.</summary>
    public bool NeedsCourseDetails => !CourseExists;

    public string SuggestedTitle => ExistingTitle ?? DetectedTitle;

    /// <summary>Qué va a pasar al confirmar, en una frase.</summary>
    public string Intent => CourseExists
        ? $"Se añadirá la versión {Version} al curso «{ExistingTitle}» que ya está en la OPS."
        : $"Se creará el curso y su versión {Version} a partir de este paquete {FormatLabel}.";
}

/// <summary>Una fila de m05_curso_host: la presencia física del curso en esta OPS.</summary>
public sealed record CourseHostRow(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("host_id")] string HostId,
    [property: JsonPropertyName("curso")] string CourseId,
    [property: JsonPropertyName("curso_titulo")] string? CourseTitle,
    [property: JsonPropertyName("curso_estado")] string? CourseStatus,
    [property: JsonPropertyName("version")] int? Version,
    [property: JsonPropertyName("formato_contenido")] string ContentFormat,
    [property: JsonPropertyName("formato_legible")] string? FormatLabel,
    [property: JsonPropertyName("manifest_tipo")] string? ManifestType,
    [property: JsonPropertyName("manifest_ref")] string? ManifestRef,
    [property: JsonPropertyName("package_identifier")] string? PackageIdentifier,
    [property: JsonPropertyName("package_ref")] string? PackageRef,
    [property: JsonPropertyName("presente_local")] bool PresentLocally,
    [property: JsonPropertyName("disponible_estudiante")] bool AvailableToStudents,
    [property: JsonPropertyName("estado_host")] string HostState,
    [property: JsonPropertyName("instalado_en")] long? InstalledAt,
    [property: JsonPropertyName("retirado_en")] long? RetiredAt)
{
    /// <summary>Las dos banderas son independientes; esto las resume para la UI.</summary>
    public string StateLabel => HostState switch
    {
        "disponible" => "Disponible para estudiantes",
        "instalado" => "Instalado · sin habilitar",
        "desinstalado" => "Desinstalado de esta OPS",
        _ => HostState,
    };

    public string VersionLabel => Version.HasValue ? $"Versión {Version}" : "Sin versión resuelta";

    public string DescriptorLabel => string.IsNullOrWhiteSpace(ManifestRef)
        ? "—" : $"{ManifestType}: {ManifestRef}";
}

/// <summary>Resultado de instalar un .zip: lo detectado, lo escrito y la presencia.</summary>
public sealed record ZipInstallResult(
    [property: JsonPropertyName("detected")] ZipPackageDetected Detected,
    [property: JsonPropertyName("install")] CoursePackageImportResult Install,
    [property: JsonPropertyName("host")] CourseHostRow Host,
    [property: JsonPropertyName("message")] string Message)
{
    public bool IsAvailableToStudents => Host.PresentLocally && Host.AvailableToStudents;

    public string Headline => Install.Idempotent
        ? $"«{Install.CourseTitle}» ya tenía la versión {Install.Version} instalada."
        : Install.CourseCreated
            ? $"«{Install.CourseTitle}» se creó desde un paquete {Detected.FormatLabel}."
            : $"«{Install.CourseTitle}» recibió la versión {Install.Version}.";
}

/// <summary>
/// Lo que aporta quien importa. El .zip declara su identificador pero no el
/// título del curso ni su marco curricular: esas son decisiones de la sede.
/// </summary>
public sealed record ZipInstallOptions(
    string HostId,
    string? Title = null,
    string? CurriculumFramework = null,
    string? CourseId = null,
    int? Version = null,
    string? Actor = null);

/// <summary>Envoltura de la vista previa: el backend responde {preview, detected}.</summary>
public sealed record ZipPackagePreviewEnvelope(
    [property: JsonPropertyName("preview")] bool Preview,
    [property: JsonPropertyName("detected")] ZipPackageDetected Detected);

/// <summary>
/// Lo académico que sobrevive a eliminar un curso. La regla del prototipo es que
/// desinstalar contenido no borra entidades académicas, así que estos tres
/// números tienen que ser idénticos antes y después.
/// </summary>
public sealed record PreservedCounts(
    [property: JsonPropertyName("students")] int Students,
    [property: JsonPropertyName("progress_rows")] int ProgressRows,
    [property: JsonPropertyName("quiz_attempts")] int QuizAttempts)
{
    public bool IsEmpty => Students == 0 && ProgressRows == 0 && QuizAttempts == 0;

    /// <summary>Lo que la tarjeta le promete al docente, en sus propios números.</summary>
    public string Summary => IsEmpty
        ? "Todavía no hay progreso de estudiantes en este curso."
        : $"{Students} {(Students == 1 ? "estudiante" : "estudiantes")} · " +
          $"{ProgressRows} {(ProgressRows == 1 ? "lección con avance" : "lecciones con avance")} · " +
          $"{QuizAttempts} {(QuizAttempts == 1 ? "intento de quiz" : "intentos de quiz")}";
}

/// <summary>Una tarjeta de la pantalla «Eliminar curso»: un curso presente en esta OPS.</summary>
public sealed record InstalledCourseCard(
    [property: JsonPropertyName("course_id")] string CourseId,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("course_state")] string? CourseState,
    [property: JsonPropertyName("version")] int? Version,
    [property: JsonPropertyName("content_format")] string ContentFormat,
    [property: JsonPropertyName("format_label")] string? FormatLabel,
    [property: JsonPropertyName("package_identifier")] string? PackageIdentifier,
    [property: JsonPropertyName("manifest_tipo")] string? ManifestType,
    [property: JsonPropertyName("installed")] bool Installed,
    [property: JsonPropertyName("available")] bool Available,
    [property: JsonPropertyName("installed_at")] long? InstalledAt,
    [property: JsonPropertyName("preserved")] PreservedCounts Preserved)
{
    public string StateLabel => Available
        ? "Disponible para estudiantes"
        : "Instalado · sin habilitar";

    public string VersionLabel => Version.HasValue
        ? $"Versión {Version} · {FormatLabel}"
        : $"Sin versión resuelta · {FormatLabel}";

    /// <summary>Lo que se conservaría, dicho antes de confirmar y no después.</summary>
    public string PreservedSummary => Preserved.Summary;

    public bool HasStudentWork => !Preserved.IsEmpty;
}

/// <summary>Envoltura del listado de cursos presentes en una OPS.</summary>
public sealed record InstalledCoursesEnvelope(
    [property: JsonPropertyName("host_id")] string HostId,
    [property: JsonPropertyName("cursos")] int Count,
    [property: JsonPropertyName("disponibles")] int AvailableCount,
    [property: JsonPropertyName("courses")] List<InstalledCourseCard> Courses);

/// <summary>El antes y el después de eliminar, para poder afirmar que nada se perdió.</summary>
public sealed record PreservedProof(
    [property: JsonPropertyName("before")] PreservedCounts Before,
    [property: JsonPropertyName("after")] PreservedCounts After,
    [property: JsonPropertyName("intact")] bool Intact);

/// <summary>
/// Resultado de eliminar un curso de esta OPS. El contenido se retira; los
/// estudiantes, el progreso y las calificaciones no se tocan.
/// </summary>
public sealed record CourseUninstallResult(
    [property: JsonPropertyName("course_id")] string CourseId,
    [property: JsonPropertyName("uninstalled_versions")] int UninstalledVersions,
    [property: JsonPropertyName("course_state")] string CourseState,
    [property: JsonPropertyName("message")] string Message,
    [property: JsonPropertyName("preserved")] PreservedProof Preserved,
    [property: JsonPropertyName("hosts")] List<CourseHostRow> Hosts)
{
    /// <summary>Ninguna fila sigue presente: el contenido salió de esta OPS.</summary>
    public bool ContentRemoved => Hosts.All(h => !h.PresentLocally);

    /// <summary>Nadie puede abrirlo: la bandera de disponibilidad quedó apagada.</summary>
    public bool NoLongerAvailable => Hosts.All(h => !h.AvailableToStudents);

    public string Headline => $"El contenido se retiró de esta OPS.";

    public string PreservedLabel => Preserved.Intact
        ? $"Se conservó todo: {Preserved.After.Summary}"
        : "ATENCIÓN: los conteos cambiaron. Algo académico se perdió.";
}
