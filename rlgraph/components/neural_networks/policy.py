# Copyright 2018 The RLgraph authors. All Rights Reserved.
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

from rlgraph import get_backend
from rlgraph.utils.rlgraph_error import RLGraphError
from rlgraph.spaces import IntBox, FloatBox
from rlgraph.components.component import Component
from rlgraph.components.common.synchronizable import Synchronizable
from rlgraph.components.common.dict_merger import DictMerger
from rlgraph.components.common.container_splitter import ContainerSplitter
from rlgraph.components.distributions import Normal, Categorical
from rlgraph.components.neural_networks.neural_network import NeuralNetwork
from rlgraph.components.action_adapters.action_adapter import ActionAdapter
from rlgraph.components.action_adapters.dueling_action_adapter import DuelingActionAdapter
from rlgraph.components.action_adapters.baseline_action_adapter import BaselineActionAdapter
from rlgraph.components.layers.preprocessing.reshape import ReShape
from rlgraph.utils.util import unify_nn_and_rnn_api_output

if get_backend() == "tf":
    import tensorflow as tf
elif get_backend() == "pytorch":
    import torch


class Policy(Component):
    """
    A Policy is a Component without own graph_fns that contains a NeuralNetwork with an attached ActionAdapter
    followed by a Distribution Component.

    API:
        get_action(nn_input, internal_states, max_likelihood) -> (action, last_internals).
            Single action based on the neural network input AND `self.max_likelihood`.
            If True, returns a deterministic (max_likelihood) sample, if False, returns a stochastic sample.
        get_nn_output(nn_input, internal_states): The raw output of the neural network (before it's cleaned-up and passed through
            our ActionAdapter).
        get_action_layer_output(nn_input, internal_states) (SingleDataOp): The raw output of the action layer of the
            ActionAdapter.
        get_q_values(nn_input, internal_states): The Q-values (action-space shaped) as calculated by the action-adapter.
        get_logits_parameters_log_probs (nn_input, internal_states): See ActionAdapter Component.
            action_layer_output_reshaped (SingleDataOp): The action layer output, reshaped according to the action
                    space.
            parameters (SingleDataOp): The parameters (probabilities) for retrieving an actual action from
                our distribution object (or directly via argmax if max-likelihood is True).
            log_probs (SingleDataOp): The log(parameters).
        get_max_likelihood_action(nn_input, internal_states): See get_action, but with max_likelihood force set to True.
        get_stochastic_action: See get_action, but with max_likelihood force set to False.
        entropy: See Distribution component.

        Optional:
            # TODO: Fix this and automatically forward all action adapter's API methods (with the preceding NN call)
            # TODO: to the policy.
            If action_adapter is a DuelingActionAdapter:
                get_dueling_output:
                    state_value (SingleDataOp): The state value diverged from the first output node of the previous
                        layer.
                    advantage_values (SingleDataOp): The advantage values (already reshaped) for the different actions.
                    q_values (SingleDataOp): The Q-values (already reshaped) for the different state-action pairs.
                        Calculated according to the dueling layer logic.
            If action_adapter is a BaselineActionAdapter:
                get_baseline_output:
                    state_value (SingleDataOp): The state value diverged from the first output node of the previous
                        layer.
                    logits (SingleDataOp): The (action-space reshaped, but otherwise raw) logits.
    """
    # TODO: change `neural_network` into unified name `network_spec`.
    def __init__(self, neural_network, action_space=None, writable=False, action_adapter_spec=None,
                 max_likelihood=True, scope="policy", **kwargs):
        """
        Args:
            neural_network (Union[NeuralNetwork,dict]): The NeuralNetwork Component or a specification dict to build
                one.
            action_space (Space): The action Space within which this Component will create actions.
            writable (bool): Whether this Policy can be synced to by another (equally structured) Policy.
                Default: False.
            action_adapter_spec (Optional[dict]): A spec-dict to create an ActionAdapter. Use None for the default
                ActionAdapter object.
            max_likelihood (bool): Whether to pick actions according to the max-likelihood value or via sampling.
                Default: True.
        """
        super(Policy, self).__init__(scope=scope, **kwargs)

        self.neural_network = NeuralNetwork.from_spec(neural_network)
        self.writable = writable
        if action_space is None:
            self.action_adapter = ActionAdapter.from_spec(action_adapter_spec)
            action_space = self.action_adapter.action_space
        else:
            self.action_adapter = ActionAdapter.from_spec(action_adapter_spec, action_space=action_space)
        self.action_space = action_space
        self.max_likelihood = max_likelihood

        # TODO: Hacky trick to implement IMPALA post-LSTM256 time-rank folding and unfolding.
        # TODO: Replace entirely via sonnet-like BatchApply Component.
        is_impala = "IMPALANetwork" in type(self.neural_network).__name__
        if is_impala:
            self.time_rank_folder = ReShape(fold_time_rank=True, scope="time-rank-fold")
            self.time_rank_unfolder_v = ReShape(unfold_time_rank=True, time_major=True, scope="time-rank-unfold-v")
            self.time_rank_unfolder_a_probs = ReShape(unfold_time_rank=True, time_major=True, scope="time-rank-unfold-a-probs")
            self.time_rank_unfolder_logits = ReShape(unfold_time_rank=True, time_major=True, scope="time-rank-unfold-logits")
            self.time_rank_unfolder_log_probs = ReShape(unfold_time_rank=True, time_major=True, scope="time-rank-unfold-log-probs")

        # Add API-method to get dueling output (if we use a dueling layer).
        if isinstance(self.action_adapter, DuelingActionAdapter):
            #def get_dueling_output(self, nn_input, internal_states=None):
            #    nn_output, last_internals = unify_nn_and_rnn_api_output(
            #        self.call(self.neural_network.apply, nn_input, internal_states)
            #    )
            #    state_value, advantages, q_values = self.call(self.action_adapter.get_dueling_output, nn_output)
            #    return (state_value, advantages, q_values, last_internals) if last_internals is not None else \
            #        (state_value, advantages, q_values)

            #self.define_api_method("get_dueling_output", get_dueling_output)

            def get_q_values(self, nn_input, internal_states=None):
                nn_output, last_internals = unify_nn_and_rnn_api_output(
                    self.call(self.neural_network.apply, nn_input, internal_states)
                )
                #_, _, q = self.call(self.action_adapter.get_dueling_output, nn_output)
                #return (q, last_internals) if last_internals is not None else q
                q_values, _, _ = self.call(self.action_adapter.get_logits_parameters_log_probs, nn_output)
                return (q_values, last_internals) if last_internals is not None else q_values

        # Add API-method to get baseline output (if we use an extra value function baseline node).
        elif isinstance(self.action_adapter, BaselineActionAdapter):
            def get_baseline_output(self, nn_input, internal_states=None):
                nn_output, last_internals = unify_nn_and_rnn_api_output(
                    self.call(self.neural_network.apply, nn_input, internal_states)
                )
                state_value, logits = self.call(self.action_adapter.get_state_values_and_logits, nn_output)
                return (state_value, logits, last_internals) if last_internals is not None else (state_value, logits)

            self.define_api_method("get_baseline_output", get_baseline_output)

            def get_state_values_logits_parameters_log_probs(self, nn_input, internal_states=None):
                nn_output, last_internals = unify_nn_and_rnn_api_output(
                    self.call(self.neural_network.apply, nn_input, internal_states)
                )

                # TODO: IMPALA attempt to speed up final pass after LSTM.
                if is_impala:
                    nn_output = self.call(self.time_rank_folder.apply, nn_output)

                state_values, logits, probs, log_probs = self.call(self.action_adapter.get_state_values_logits_parameters_log_probs, nn_output)

                # TODO: IMPALA attempt to speed up final pass after LSTM.
                if is_impala:
                    state_values = self.call(self.time_rank_unfolder_v.apply, state_values, nn_output)
                    logits = self.call(self.time_rank_unfolder_logits.apply, logits, nn_output)
                    probs = self.call(self.time_rank_unfolder_a_probs.apply, probs, nn_output)
                    log_probs = self.call(self.time_rank_unfolder_log_probs.apply, log_probs, nn_output)

                return (state_values, logits, probs, log_probs, last_internals) if last_internals is not None else \
                    (state_values, logits, probs, log_probs)

            self.define_api_method("get_state_values_logits_parameters_log_probs",
                                   get_state_values_logits_parameters_log_probs)

            def get_q_values(self, nn_input, internal_states=None):
                nn_output, last_internals = unify_nn_and_rnn_api_output(
                    self.call(self.neural_network.apply, nn_input, internal_states)
                )
                _, logits = self.call(self.action_adapter.get_state_values_and_logits, nn_output)
                return (logits, last_internals) if last_internals is not None else logits
        else:
            def get_q_values(self, nn_input, internal_states=None):
                nn_output, last_internals = unify_nn_and_rnn_api_output(
                    self.call(self.neural_network.apply, nn_input, internal_states)
                )
                logits, _, _ = self.call(self.action_adapter.get_logits_parameters_log_probs, nn_output)
                return (logits, last_internals) if last_internals is not None else logits

        self.define_api_method("get_q_values", get_q_values)

        # Figure out our Distribution.
        if isinstance(action_space, IntBox):
            self.distribution = Categorical()
        # Continuous action space -> Normal distribution (each action needs mean and variance from network).
        elif isinstance(action_space, FloatBox):
            self.distribution = Normal()
        else:
            raise RLGraphError("ERROR: `action_space` is of type {} and not allowed in {} Component!".
                               format(type(action_space).__name__, self.name))

        self.add_components(
            self.neural_network, self.action_adapter, self.distribution
        )

        if is_impala:
            self.add_components(
                self.time_rank_folder, self.time_rank_unfolder_v, self.time_rank_unfolder_a_probs,
                self.time_rank_unfolder_log_probs, self.time_rank_unfolder_logits
            )

        # Add Synchronizable API to ours.
        if self.writable:
            self.add_components(Synchronizable(), expose_apis="sync")

    # Define our interface.
    def get_action(self, nn_input, internal_states=None, max_likelihood=None):
        nn_output, last_internals = unify_nn_and_rnn_api_output(
            self.call(self.neural_network.apply, nn_input, internal_states)
        )

        max_likelihood = self.max_likelihood if max_likelihood is None else max_likelihood
        # Skip our distribution, iff discrete action-space and max-likelihood acting (greedy).
        # In that case, one does not need to create a distribution in the graph each act (only to get the argmax
        # over the logits, which is the same as the argmax over the probabilities (or log-probabilities)).
        if max_likelihood is True and isinstance(self.action_space, IntBox):
            logits, _, _ = self.call(self.action_adapter.get_logits_parameters_log_probs, nn_output)
            sample = self.call(self._graph_fn_get_max_likelihood_action_wo_distribution, logits)
        else:
            _, parameters, _ = self.call(self.action_adapter.get_logits_parameters_log_probs, nn_output)
            sample = self.call(self.distribution.draw, parameters, max_likelihood)
        return (sample, last_internals) if last_internals is not None else sample

    def get_nn_output(self, nn_input, internal_states=None):
        nn_output, last_internals = unify_nn_and_rnn_api_output(
            self.call(self.neural_network.apply, nn_input, internal_states)
        )
        return (nn_output, last_internals) if last_internals is not None else nn_output

    def get_action_layer_output(self, nn_input, internal_states=None):
        nn_output, last_internals = unify_nn_and_rnn_api_output(
            self.call(self.neural_network.apply, nn_input, internal_states)
        )
        action_layer_output = self.call(self.action_adapter.get_action_layer_output, nn_output)
        return (action_layer_output, last_internals) if last_internals is not None else action_layer_output

    def get_logits_parameters_log_probs(self, nn_input, internal_states=None):
        nn_output, last_internals = unify_nn_and_rnn_api_output(
            self.call(self.neural_network.apply, nn_input, internal_states)
        )
        logits, parameters, log_probs = self.call(self.action_adapter.get_logits_parameters_log_probs, nn_output)
        return (logits, parameters, log_probs, last_internals) if last_internals is not None \
            else (logits, parameters, log_probs)

    def get_entropy(self, nn_input, internal_states=None):
        nn_output, last_internals = unify_nn_and_rnn_api_output(
            self.call(self.neural_network.apply, nn_input, internal_states)
        )
        _, parameters, _ = self.call(self.action_adapter.get_logits_parameters_log_probs, nn_output)
        entropy = self.call(self.distribution.entropy, parameters)
        return (entropy, last_internals) if last_internals is not None else entropy

    def get_max_likelihood_action(self, nn_input, internal_states=None):
        nn_output, last_internals = unify_nn_and_rnn_api_output(
            self.call(self.neural_network.apply, nn_input, internal_states)
        )

        #max_likelihood = self.max_likelihood if max_likelihood is None else max_likelihood
        # print("Policy - max likelihood option enabled = {}, self.max_likelihood = {}".format(max_likelihood,
        #                                                                                    self.max_likelihood))
        #if max_likelihood is True and isinstance(self.action_space, IntBox):

        if isinstance(self.action_space, IntBox):
            logits, _, _ = self.call(self.action_adapter.get_logits_parameters_log_probs, nn_output)
            sample = self.call(self._graph_fn_get_max_likelihood_action_wo_distribution, logits)
        else:
            _, parameters, _ = self.call(self.action_adapter.get_logits_parameters_log_probs, nn_output)
            sample = self.call(self.distribution.sample_deterministic, parameters)

        return (sample, last_internals) if last_internals is not None else sample

    def get_stochastic_action(self, nn_input, internal_states=None):
        nn_output, last_internals = unify_nn_and_rnn_api_output(
            self.call(self.neural_network.apply, nn_input, internal_states)
        )
        _, parameters, _ = self.call(self.action_adapter.get_logits_parameters_log_probs, nn_output)
        sample = self.call(self.distribution.sample_stochastic, parameters)
        return (sample, last_internals) if last_internals is not None else sample

    def _graph_fn_get_max_likelihood_action_wo_distribution(self, logits):
        """
        Use this function only for discrete action spaces to circumvent using a full-blown
        backend-specific distribution object (e.g. tf.distribution.Multinomial).

        Args:
            logits (SingleDataOpDict): Logits over which to pick the argmax (greedy action).

        Returns:
            SingleDataOp: The argmax over the last rank of the input logits.
        """
        if get_backend() == "tf":
            return tf.argmax(logits, axis=-1, output_type=tf.int32)
        elif get_backend() == "pytorch":
            return torch.argmax(logits, dim=-1).int()
