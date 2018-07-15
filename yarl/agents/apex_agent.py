# Copyright 2018 The YARL-Project, All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from yarl.agents import DQNAgent


class ApexAgent(DQNAgent):
    """
    Ape-X is a DQN variant designed for large scale distributed execution where many workers
    share a distributed prioritized experience replay.

    Paper: https://arxiv.org/abs/1803.00933

    The distinction to standard DQN is mainly that Ape-X needs to provide additional operations
    to enable external updates of priorities. Ape-X also enables per default dueling and double
    DQN.
    """
    def __init__(self, discount=0.98, memory_spec=None, **kwargs):
        """
        Args:
            discount (float): The discount factor (gamma).
            memory_spec (Optional[dict,Memory]): The spec for the Memory to use for the DQN algorithm.
        """
        assert memory_spec["type"] == "prioritized_replay"
        super(ApexAgent, self).__init__(discount=discount, memory_spec=memory_spec, **kwargs)

        # Apex uses train time steps for syncing.
        self.train_time_steps = 0

    # def define_api_methods(self, preprocessor, merger, memory, splitter, policy, target_policy, exploration,
    #                        loss_function, optimizer):
    #
    #     # State from environment to action pathway.
    #     def get_action_and_preprocessed_state(self_, states, time_step, use_exploration=True):
    #         preprocessed_states = self_.call(preprocessor.preprocess, states)
    #         sample_deterministic = self_.call(policy.sample_deterministic, preprocessed_states)
    #         sample_stochastic = self_.call(policy.sample_stochastic, preprocessed_states)
    #         actions = self_.call(exploration.get_action, sample_deterministic, sample_stochastic,
    #                              time_step, use_exploration)
    #         return actions, preprocessed_states
    #
    #     self.core_component.define_api_method("get_action_and_preprocessed_state", get_action_and_preprocessed_state)
    #
    #     # Insert into memory pathway.
    #     def insert_records(self_, states, actions, rewards, terminals):
    #         preprocessed_states = self_.call(preprocessor.preprocess, states)
    #         records = self_.call(merger.merge, preprocessed_states, actions, rewards, terminals)
    #         return self_.call(memory.insert_records, records)
    #
    #     self.core_component.define_api_method("insert_records", insert_records)
    #
    #     # Syncing target-net.
    #     def sync_target_qnet(self_):
    #         policy_vars = self_.call(policy._variables)
    #         return self_.call(target_policy.sync, policy_vars)
    #
    #     self.core_component.define_api_method("sync_target_qnet", sync_target_qnet)
    #
    #     # Learn from memory.
    #     def update_from_memory(self_):
    #         records = self_.call(memory.get_records, self.update_spec["batch_size"])
    #
    #         states, actions, rewards, terminals, next_states = self_.call(splitter.split, records)
    #
    #         # Get the different Q-values.
    #         q_values_s = self_.call(policy.get_q_values, states)
    #         qt_values_sp = self_.call(target_policy.get_q_values, next_states)
    #         q_values_sp = self_.call(policy.get_q_values, next_states)
    #
    #         loss = self_.call(loss_function.loss, q_values_s, actions, rewards, terminals,
    #                           qt_values_sp, q_values_sp)
    #
    #         policy_vars = self_.call(policy._variables)
    #         # TODO: For multi-GPU, the final-loss will probably have to come from the optimizer.
    #         return self_.call(optimizer.step, policy_vars, loss), loss, records, q_values_s
    #
    #     self.core_component.define_api_method("update_from_memory", update_from_memory)
    #
    #     # Learn from an external batch.
    #     def update_from_external_batch(self_, states, actions, rewards, terminals, next_states):
    #         preprocessed_s = self_.call(preprocessor.preprocess, states)
    #         preprocessed_sp = self_.call(preprocessor.preprocess, next_states)
    #
    #         # Get the different Q-values.
    #         q_values_s = self_.call(policy.get_q_values, preprocessed_s)
    #         qt_values_sp = self_.call(target_policy.get_q_values, preprocessed_sp)
    #         q_values_sp = self_.call(policy.get_q_values, preprocessed_sp)
    #
    #         loss = self_.call(loss_function.loss, q_values_s, actions, rewards, terminals,
    #                           qt_values_sp, q_values_sp)
    #         policy_vars = self_.call(policy._variables)
    #         # TODO:For multi-GPU, the final-loss will probably have to come from the optimizer.
    #         return self_.call(optimizer.step, policy_vars, loss), loss
    #
    #     self.core_component.define_api_method("update_from_external_batch", update_from_external_batch)
    #
    #     # def update_priorities(self_, indices, loss):
    #     #     return self_.call(memory._graph_fn_update_records, indices, loss)
    #     #
    #     # self.core_component.define_api_method("update_priorities", update_priorities)
    #
    # def get_action(self, states, use_exploration=True, return_preprocessed_states=False):
    #     batched_states = self.state_space.batched(states)
    #     remove_batch_rank = batched_states.ndim == np.asarray(states).ndim + 1
    #     # Increase timesteps by the batch size (number of states in batch).
    #     self.timesteps += len(batched_states)
    #     # Control, which return value to "pull".
    #     ret = self.graph_executor.execute(
    #         ("get_action_and_preprocessed_state",
    #          [batched_states, self.timesteps, use_exploration],
    #          [0] if return_preprocessed_states is False else [0, 1])  # 0=action, 1=preprocessed_states
    #     )
    #     if return_preprocessed_states:
    #         if remove_batch_rank:
    #             return strip_list(ret[0]), strip_list(ret[1])
    #         else:
    #             return ret[0], ret[1]
    #     return strip_list(ret) if remove_batch_rank else ret

    # def update_priorities(self, indices, loss):
    #     """
    #     Updates priorities of provided indices in replay memory via externally
    #     provided loss.
    #
    #     Args:
    #         indices (ndarray): Indices to update in replay memory.
    #         loss (ndarray):  Loss values for indices.
    #     """
    #     self.graph_executor.execute(("update_priorities", [indices, loss]))

    # def _observe_graph(self, states, actions, internals, rewards, terminals):
    #     self.graph_executor.execute(("insert_records", [states, actions, rewards, terminals]))

    def update(self, batch=None):
        # In apex, syncing is based on num steps trained, not steps sampled.
        sync_call = None
        if (self.train_time_steps - 1) % self.update_spec["sync_interval"] == 0:
            sync_call = "sync_target_qnet"

        return_ops = [0, 1]
        if batch is None:
            # Add some additional return-ops to pull (left out normally for performance reasons).
            ret = self.graph_executor.execute(("update_from_memory", None, return_ops), sync_call)

            # Remove unnecessary return dicts (e.g. sync-op).
            if isinstance(ret, dict):
                ret = ret["update_from_memory"]
        else:
            # Add some additional return-ops to pull (left out normally for performance reasons).

            batch_input = dict(
                external_batch_states=batch["states"],
                external_batch_actions=batch["actions"],
                external_batch_rewards=batch["rewards"],
                external_batch_terminals=batch["terminals"],
                external_batch_next_states=batch["next_states"]
            )
            ret = self.graph_executor.execute(("update_from_external_batch", batch_input), sync_call)

            # Remove unnecessary return dicts (e.g. sync-op).
            if isinstance(ret, dict):
                ret = ret["update_from_memory"]

        # [1]=the loss (0=update noop)
        self.train_time_steps += 1
        return ret[1]

    def __repr__(self):
        return "ApexAgent"
