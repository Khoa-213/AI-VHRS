import '../i18n/tech_strings.dart';
import 'tech_models.dart';

/// QC checklist and photo slots (FE `pages/tech/qcItems.ts`).

class QcItem {
  final String id;
  final String title;
  final String detail;
  const QcItem(this.id, this.title, this.detail);
}

class QcGroup {
  final String id;
  final String title;
  final List<QcItem> items;
  const QcGroup(this.id, this.title, this.items);
}

/// Everything the technician checks before the customer sees the result, grouped by where they look.
List<QcGroup> qcGroups(TechOrder o, T t) {
  final sp = o.spec;
  final pieces = sp.qty == 0 ? 1 : sp.qty;
  final layout = t.tn(o.layout.label);
  return [
    QcGroup('sheet', t('qc.sheet'), [
      QcItem('paper', t('qc.paper', {'name': t.tn(sp.paper)}),
          t('qc.paperDetail', {'type': t.tn(sp.type), 'land': sp.land ? t('qc.landscape') : ''})),
      QcItem('layout', t('qc.layout', {'name': layout}), t('qc.layoutDetail')),
      QcItem('bleed', t('qc.bleed'), t('qc.bleedDetail')),
    ]),
    QcGroup('writing', t('qc.writing'), [
      QcItem('text', t('qc.text'), t('qc.textDetail')),
      QcItem('marks', t('qc.marks'), t('qc.marksDetail')),
      QcItem('strokes', t('qc.strokes'), t('qc.strokesDetail')),
      QcItem('ink', t('qc.ink', {'name': t.tn(sp.ink)}), t('qc.inkDetail', {'pen': t.tn(sp.pen)})),
      QcItem('marksout', t('qc.marksOut'), t('qc.marksOutDetail')),
    ]),
    QcGroup('pieces', t('qc.pieces'), [
      QcItem(
        'count',
        pieces > 1 ? t('qc.countMany', {'n': pieces}) : t('qc.countOne'),
        t(pieces > 1 ? 'qc.countManyDetail' : 'qc.countOneDetail'),
      ),
      QcItem('dry', t('qc.dry'), t('qc.dryDetail')),
      QcItem('pack', t('qc.pack'), t('qc.packDetail')),
    ]),
  ];
}

class PhotoSlot {
  final String id;
  final String label;
  final String hint;
  final bool required;
  const PhotoSlot(this.id, this.label, this.hint, {required this.required});
}

const photoSlots = [
  PhotoSlot('sheet', 'Whole sheet', 'Flat, all four corners visible', required: true),
  PhotoSlot('close', 'Close-up', 'A few words, in focus', required: true),
  PhotoSlot('packed', 'Packed', 'Optional, the stack before it ships', required: false),
];

const qcFailReasons = ['Ink smudge', 'Missing strokes', 'Wrong paper', 'Text mismatch', 'Pen skipped', 'Other'];

/// Preflight checks before the real robot may start (FE `RobotPreview.tsx`).
const preflightChecks = ['paper', 'pen', 'ink', 'calibration', 'clear'];

/// Fake evaluation numbers, same formula as FE `evaluate.ts`.
int strokeCount(String text) => ((text.isEmpty ? 12 : text.length) * 2.6 + 12).round();
