// RuntimeNavModule.cs - Exiled plugin spawning a dummy with runtime navmesh
using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.AI;
using System.Threading.Tasks;
using Prometheus;
using Exiled.API.Features;
using Exiled.Events.EventArgs;
using Exiled.Events.EventArgs.Server;

namespace SentientOS.UnityNav
{
    public sealed class RuntimeNavModule : Plugin<Config>
    {
        public override string Name => "RuntimeNavModule";
        public override string Author => "Codex";
        public override Version Version => new Version(1, 0, 0);
        public override Version RequiredExiledVersion => new Version(8, 0, 0);

        public static readonly Counter NavPathTotal = Metrics.CreateCounter(
            "sentientos_nav_paths_total",
            "Total nav paths the dummy has computed");

        private NavMeshData _navData;
        private NavMeshAgent _agent;
        private Dummy _dummy;
        private readonly List<Vector3> _roomCenters = new();

        public override void OnEnabled()
        {
            Exiled.Events.Handlers.Server.RoundStarted += OnRoundStarted;
            Exiled.Events.Handlers.Server.RoundEnded += OnRoundEnded;
            base.OnEnabled();
        }

        public override void OnDisabled()
        {
            Exiled.Events.Handlers.Server.RoundStarted -= OnRoundStarted;
            Exiled.Events.Handlers.Server.RoundEnded -= OnRoundEnded;
            base.OnDisabled();
        }

        private async void OnRoundStarted()
        {
            GameObject roomManager = GameObject.Find("RoomManager");
            if (roomManager == null)
                return;

            var buildResult = await RecastNavBuilder.BuildAsync(roomManager);
            _navData = buildResult.Data;
            var centers = buildResult.Centers;
            _roomCenters.Clear();
            _roomCenters.AddRange(centers);
            NavMesh.AddNavMeshData(_navData);

            _dummy = Dummy.Spawn(roomManager.transform.position, RoleTypeId.Tutorial);
            _agent = _dummy.GameObject.AddComponent<NavMeshAgent>();
            _agent.speed = 4.4f;
            _agent.angularSpeed = 720f;
            _agent.acceleration = 16f;
            _agent.obstacleAvoidanceType = ObstacleAvoidanceType.NoObstacleAvoidance;
            _agent.height = 1.9f;
            _agent.radius = 0.4f;

            DoorVariant targetDoor = UnityEngine.Object.FindObjectsOfType<DoorVariant>()
                .FirstOrDefault(d => d.TargetType == DoorType.GateA && !d.IsOpen);
            Vector3 dest = targetDoor != null ? targetDoor.transform.position : _roomCenters.FirstOrDefault();
            if (dest != Vector3.zero)
            {
                _agent.SetDestination(dest);
                CathedralAudit.LogPath(_dummy.UserId, _agent.path.corners);
                NavPathTotal.Inc();
            }

            var runner = _dummy.GameObject.AddComponent<NavRunner>();
            runner.Init(_agent, _roomCenters, _dummy.UserId);
        }

        private void OnRoundEnded(RoundEndedEventArgs ev)
        {
            if (_navData != null)
            {
                NavMesh.RemoveNavMeshData(_navData);
                _navData = null;
            }
        }
    }

    internal sealed class NavRunner : MonoBehaviour
    {
        private NavMeshAgent _agent;
        private List<Vector3> _rooms;
        private string _userId;

        public void Init(NavMeshAgent agent, List<Vector3> rooms, string userId)
        {
            _agent = agent;
            _rooms = rooms;
            _userId = userId;
        }

        private void Update()
        {
            if (_agent.pathPending)
                return;

            if (_agent.remainingDistance >= 0f && _agent.remainingDistance < 0.5f)
            {
                Vector3 next = _rooms[UnityEngine.Random.Range(0, _rooms.Count)];
                if (next != Vector3.zero)
                {
                    _agent.SetDestination(next);
                    CathedralAudit.LogPath(_userId, _agent.path.corners);
                    RuntimeNavModule.NavPathTotal.Inc();
                }
            }
        }
    }
}
