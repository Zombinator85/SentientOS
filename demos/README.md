# Consensus Demo Bundle

This directory contains a minimal Sentient Script plan that can be used to exercise the hardened verifier consensus flow. The demo walks an operator through starting consensus, restarting the relay, and observing resume/cancel/finalise controls from the console.

## Files

- `consensus/small_plan.json` – A tiny script with deterministic outcomes that is easy to replay and aggregate.

## Running the demo

1. **Submit the verification job**
   ```bash
   curl -X POST \
     -H "Content-Type: application/json" \
     -H "X-Node-Token: $NODE_TOKEN" \
     -d @demos/consensus/small_plan.json \
     http://localhost:8000/admin/verify/submit
   ```
   The response includes `job_id` and `script_hash`.

2. **Start consensus with two out of three participants**
   ```bash
   curl -X POST \
     -H "Content-Type: application/json" \
     -H "X-Node-Token: $NODE_TOKEN" \
     -H "X-CSRF-Token: $(curl -s http://localhost:8000/admin/status | jq -r .csrf_token)" \
     -d '{
       "job_id": "<JOB_ID>",
       "quorum_k": 2,
       "quorum_n": 3
     }' \
     http://localhost:8000/admin/verify/consensus/submit
   ```

3. **Restart the relay while votes are still pending**
   ```bash
   supervisorctl stop sentient-relay
   supervisorctl start sentient-relay
   ```
   When the relay boots it calls `resume_inflight_jobs()` and broadcasts the restored snapshot.

4. **Observe the console**
   - The consensus card shows a blue “Running” chip and a **Resumed** badge.
   - Use the new **Cancel** or **Force Finalize** buttons to exercise administrative controls.
   - The vote table updates with retry counts, last error messages, and backoff hints while the mesh retries.

5. **Complete the quorum**
   Submit remaining votes (either via mesh participants or `/mesh/verify/submit_vote`). Once the quorum is satisfied, the job finalises, metrics are updated, and the card switches to a green **Finalized** chip.

This flow demonstrates restart-resume safety, administrative cancellation/finalisation, and the improved observability that accompanies the hardened consensus pipeline.
