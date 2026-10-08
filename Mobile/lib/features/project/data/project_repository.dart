import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants/api_constants.dart';
import '../../../core/network/dio_client.dart';
import '../domain/models/project.dart';

/// Repository for project CRUD operations.
abstract class ProjectRepository {
  Future<List<Project>> getProjects({int page = 1, int pageSize = 20});
  Future<Project> getProjectById(String id);
  Future<Project> createProject({
    required String name,
    required String paperSizeId,
    required String penTypeId,
  });
  Future<Project> updateProject(String id, {String? name, String? status});
  Future<void> deleteProject(String id);
}

class ProjectRepositoryImpl implements ProjectRepository {
  final DioClient _client;

  ProjectRepositoryImpl({required DioClient client}) : _client = client;

  static final List<Project> _mockProjects = [
    Project(
      id: 'proj-001',
      name: 'Thư mời cưới cao cấp - Hoài An & Minh Đức',
      paperSizeId: 'A5',
      penTypeId: 'fountain',
      status: 'completed',
      inputMethod: 'canvas_draw',
      estimatedPrice: 120000,
      createdAt: DateTime.now().subtract(const Duration(days: 2)),
    ),
    Project(
      id: 'proj-002',
      name: 'Thiệp cảm ơn tri ân đối tác VIP',
      paperSizeId: 'A4',
      penTypeId: 'gel',
      status: 'processing',
      inputMethod: 'text_font',
      estimatedPrice: 75000,
      createdAt: DateTime.now().subtract(const Duration(hours: 4)),
    ),
    Project(
      id: 'proj-003',
      name: 'Bản thảo chữ ký số nghệ thuật',
      paperSizeId: 'Letter',
      penTypeId: 'ballpoint',
      status: 'draft',
      inputMethod: 'image_upload',
      estimatedPrice: 45000,
      createdAt: DateTime.now().subtract(const Duration(minutes: 25)),
    ),
  ];

  @override
  Future<List<Project>> getProjects({int page = 1, int pageSize = 20}) async {
    try {
      final response = await _client.get<Map<String, dynamic>>(
        ApiConstants.projects,
        queryParameters: {'page': page, 'page_size': pageSize},
      );
      final items = response['data'] as List<dynamic>;
      return items
          .map((item) => Project.fromJson(item as Map<String, dynamic>))
          .toList();
    } catch (_) {
      // Fallback to mock projects when backend is offline
      await Future.delayed(const Duration(milliseconds: 300));
      return List<Project>.from(_mockProjects);
    }
  }

  @override
  Future<Project> getProjectById(String id) async {
    try {
      final response = await _client.get<Map<String, dynamic>>(
        ApiConstants.projectById(id),
      );
      return Project.fromJson(response);
    } catch (_) {
      return _mockProjects.firstWhere(
        (p) => p.id == id,
        orElse: () => Project(
          id: id,
          name: 'Dự án viết tay mẫu',
          paperSizeId: 'A4',
          penTypeId: 'fountain',
          status: 'draft',
          createdAt: DateTime.now(),
        ),
      );
    }
  }

  @override
  Future<Project> createProject({
    required String name,
    required String paperSizeId,
    required String penTypeId,
  }) async {
    try {
      final response = await _client.post<Map<String, dynamic>>(
        ApiConstants.projects,
        data: {
          'name': name,
          'paper_size_id': paperSizeId,
          'pen_type_id': penTypeId,
        },
      );
      return Project.fromJson(response);
    } catch (_) {
      final newProj = Project(
        id: 'proj-${DateTime.now().millisecondsSinceEpoch.toString().substring(7)}',
        name: name,
        paperSizeId: paperSizeId,
        penTypeId: penTypeId,
        status: 'draft',
        createdAt: DateTime.now(),
      );
      _mockProjects.insert(0, newProj);
      return newProj;
    }
  }

  @override
  Future<Project> updateProject(String id, {String? name, String? status}) async {
    try {
      final response = await _client.patch<Map<String, dynamic>>(
        ApiConstants.projectById(id),
        data: {
          if (name != null) 'name': name,
          if (status != null) 'status': status,
        },
      );
      return Project.fromJson(response);
    } catch (_) {
      final index = _mockProjects.indexWhere((p) => p.id == id);
      if (index != -1) {
        final current = _mockProjects[index];
        final updated = Project(
          id: current.id,
          name: name ?? current.name,
          paperSizeId: current.paperSizeId,
          penTypeId: current.penTypeId,
          status: status ?? current.status,
          inputMethod: current.inputMethod,
          thumbnailUrl: current.thumbnailUrl,
          estimatedPrice: current.estimatedPrice,
          createdAt: current.createdAt,
          updatedAt: DateTime.now(),
        );
        _mockProjects[index] = updated;
        return updated;
      }
      throw Exception('Project not found');
    }
  }

  @override
  Future<void> deleteProject(String id) async {
    try {
      await _client.delete(ApiConstants.projectById(id));
    } catch (_) {
      _mockProjects.removeWhere((p) => p.id == id);
    }
  }
}

final projectRepositoryProvider = Provider<ProjectRepository>((ref) {
  final client = ref.watch(dioClientProvider);
  return ProjectRepositoryImpl(client: client);
});
