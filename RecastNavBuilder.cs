// RecastNavBuilder.cs - runtime navmesh construction via Recast
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.AI;

namespace SentientOS.UnityNav
{
    public static class RecastNavBuilder
    {
        public static NavMeshData Build(GameObject root, out List<Vector3> roomCenters)
        {
            roomCenters = new List<Vector3>();
            var sources = new List<NavMeshBuildSource>();

            foreach (var mesh in root.GetComponentsInChildren<MeshCollider>())
            {
                if (mesh.sharedMesh == null)
                    continue;
                roomCenters.Add(mesh.bounds.center);
                var src = new NavMeshBuildSource
                {
                    shape = NavMeshBuildSourceShape.Mesh,
                    sourceObject = mesh.sharedMesh,
                    transform = mesh.transform.localToWorldMatrix,
                    area = 0
                };
                sources.Add(src);
            }

            foreach (var box in root.GetComponentsInChildren<BoxCollider>())
            {
                roomCenters.Add(box.bounds.center);
                var src = new NavMeshBuildSource
                {
                    shape = NavMeshBuildSourceShape.Box,
                    size = box.size,
                    transform = Matrix4x4.TRS(box.transform.position, box.transform.rotation, box.transform.lossyScale),
                    area = 0
                };
                sources.Add(src);
            }

            foreach (var sphere in root.GetComponentsInChildren<SphereCollider>())
            {
                roomCenters.Add(sphere.bounds.center);
                var src = new NavMeshBuildSource
                {
                    shape = NavMeshBuildSourceShape.Sphere,
                    size = Vector3.one * sphere.radius * 2f,
                    transform = Matrix4x4.TRS(sphere.transform.position, sphere.transform.rotation, sphere.transform.lossyScale),
                    area = 0
                };
                sources.Add(src);
            }

            foreach (var terrainCollider in root.GetComponentsInChildren<TerrainCollider>())
            {
                roomCenters.Add(terrainCollider.bounds.center);
                var terrain = terrainCollider.GetComponent<Terrain>();
                if (terrain != null && terrain.terrainData != null)
                {
                    var src = new NavMeshBuildSource
                    {
                        shape = NavMeshBuildSourceShape.Terrain,
                        sourceObject = terrain.terrainData,
                        transform = terrain.transform.localToWorldMatrix,
                        area = 0
                    };
                    sources.Add(src);
                }
            }

            var settings = NavMesh.GetSettingsByID(0);
            settings.agentHeight = 1.9f;
            settings.agentRadius = 0.4f;
            settings.overrideVoxelSize = true;
            settings.voxelSize = 0.3f;
            settings.overrideTileSize = true;
            settings.tileSize = 128;

            var bounds = new Bounds(root.transform.position, new Vector3(1000f, 200f, 1000f));
            var data = NavMeshBuilder.BuildNavMeshData(settings, sources, bounds, Vector3.zero, Quaternion.identity);
            return data;
        }

        public static Task<(NavMeshData Data, List<Vector3> Centers)> BuildAsync(GameObject root)
        {
            return Task.Run(() =>
            {
                var data = Build(root, out var centers);
                return (data, centers);
            });
        }
    }
}
