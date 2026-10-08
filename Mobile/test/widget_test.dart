import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_vhrs_mobile/features/project/data/project_repository.dart';
import 'package:ai_vhrs_mobile/features/project/domain/models/project.dart';
import 'package:ai_vhrs_mobile/main.dart';

/// Keeps the smoke test off the network.
class _EmptyProjectRepository implements ProjectRepository {
  @override
  Future<List<Project>> getProjects({int page = 1, int pageSize = 20}) async => [];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  testWidgets('App launches without errors', (WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          projectRepositoryProvider.overrideWithValue(_EmptyProjectRepository()),
        ],
        child: const AiVhrsApp(),
      ),
    );

    // Verify the app renders
    expect(find.byType(MaterialApp), findsOneWidget);
  });
}
