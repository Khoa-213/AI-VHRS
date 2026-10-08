import 'package:equatable/equatable.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/network_exceptions.dart';
import '../data/project_repository.dart';
import '../domain/models/project.dart';

/// State for the project list.
class ProjectListState extends Equatable {
  final List<Project> projects;
  final bool isLoading;
  final bool isLoadingMore;
  final String? error;
  final int currentPage;
  final bool hasReachedEnd;

  const ProjectListState({
    this.projects = const [],
    this.isLoading = false,
    this.isLoadingMore = false,
    this.error,
    this.currentPage = 1,
    this.hasReachedEnd = false,
  });

  ProjectListState copyWith({
    List<Project>? projects,
    bool? isLoading,
    bool? isLoadingMore,
    String? error,
    int? currentPage,
    bool? hasReachedEnd,
  }) {
    return ProjectListState(
      projects: projects ?? this.projects,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      error: error,
      currentPage: currentPage ?? this.currentPage,
      hasReachedEnd: hasReachedEnd ?? this.hasReachedEnd,
    );
  }

  @override
  List<Object?> get props =>
      [projects, isLoading, isLoadingMore, error, currentPage, hasReachedEnd];
}

/// StateNotifier for the project dashboard.
class ProjectListNotifier extends StateNotifier<ProjectListState> {
  final ProjectRepository _repository;

  ProjectListNotifier({required ProjectRepository repository})
      : _repository = repository,
        super(const ProjectListState());

  /// Loads the first page of projects.
  Future<void> loadProjects() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final projects = await _repository.getProjects(page: 1);
      state = state.copyWith(
        projects: projects,
        isLoading: false,
        currentPage: 1,
        hasReachedEnd: projects.length < 20,
      );
    } on NetworkException catch (e) {
      state = state.copyWith(isLoading: false, error: e.message);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  /// Loads the next page of projects (pagination).
  Future<void> loadMore() async {
    if (state.isLoadingMore || state.hasReachedEnd) return;

    state = state.copyWith(isLoadingMore: true);
    try {
      final nextPage = state.currentPage + 1;
      final moreProjects = await _repository.getProjects(page: nextPage);
      state = state.copyWith(
        projects: [...state.projects, ...moreProjects],
        isLoadingMore: false,
        currentPage: nextPage,
        hasReachedEnd: moreProjects.length < 20,
      );
    } on NetworkException catch (e) {
      state = state.copyWith(isLoadingMore: false, error: e.message);
    } catch (e) {
      state = state.copyWith(isLoadingMore: false, error: e.toString());
    }
  }

  /// Creates a new project and prepends it to the list.
  Future<Project?> createProject({
    required String name,
    required String paperSizeId,
    required String penTypeId,
  }) async {
    try {
      final project = await _repository.createProject(
        name: name,
        paperSizeId: paperSizeId,
        penTypeId: penTypeId,
      );
      state = state.copyWith(projects: [project, ...state.projects]);
      return project;
    } on NetworkException catch (e) {
      state = state.copyWith(error: e.message);
      return null;
    }
  }

  /// Removes a project from the list.
  Future<bool> deleteProject(String id) async {
    try {
      await _repository.deleteProject(id);
      state = state.copyWith(
        projects: state.projects.where((p) => p.id != id).toList(),
      );
      return true;
    } on NetworkException catch (e) {
      state = state.copyWith(error: e.message);
      return false;
    }
  }
}

final projectListProvider =
    StateNotifierProvider<ProjectListNotifier, ProjectListState>((ref) {
  final repository = ref.watch(projectRepositoryProvider);
  return ProjectListNotifier(repository: repository);
});
