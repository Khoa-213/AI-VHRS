import '../../../core/widgets/line_art.dart';

/// The three ways a customer can hand their words to the robot.
enum InputMode {
  image(
    title: 'Upload handwriting photo',
    description:
        'Scan handwritten notes. AI extracts the stroke trajectory and Vietnamese diacritics automatically.',
    tag: 'AI',
    glyph: ModeGlyphKind.photo,
  ),
  text(
    title: 'Text + single-line font',
    description: 'Type your words and pick a curated single-line calligraphy style.',
    tag: 'Vector',
    glyph: ModeGlyphKind.text,
  ),
  canvas(
    title: 'Live canvas drawing',
    description:
        'Draw or sign freely with finger or stylus. Every stroke is captured exactly for the robot arm.',
    tag: 'Real-time',
    glyph: ModeGlyphKind.canvas,
  );

  final String title;
  final String description;
  final String tag;
  final ModeGlyphKind glyph;

  const InputMode({
    required this.title,
    required this.description,
    required this.tag,
    required this.glyph,
  });

  static InputMode? fromName(String? name) {
    for (final mode in values) {
      if (mode.name == name) return mode;
    }
    return null;
  }
}
