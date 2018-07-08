#!/usr/bin/python3
import argparse
import gym
import numpy as np
import tensorflow as tf
from network_models.policy_net import Policy_net
from network_models.discriminator import Discriminator
from algo.ppo import PPOTrain
import pdb


def argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--logdir', help='log directory', default='log/train/gail')
    parser.add_argument('--savedir', help='save directory', default='trained_models/gail')
    parser.add_argument('--gamma', default=0.95)
    parser.add_argument('--iteration', default=int(1e4))
    return parser.parse_args()


def main(args):
    env = gym.make('CartPole-v0')
    env.seed(0)
    ob_space = env.observation_space
    Policy = Policy_net('policy', env)
    Old_Policy = Policy_net('old_policy', env)
    PPO = PPOTrain(Policy, Old_Policy, gamma=args.gamma)
    D = Discriminator(env)

    expert_observations = np.genfromtxt('trajectory/observations.csv')
    expert_actions = np.genfromtxt('trajectory/actions.csv', dtype=np.int32)

    saver = tf.train.Saver()
    

    with tf.Session() as sess:
        writer = tf.summary.FileWriter(args.logdir, sess.graph)
        sess.run(tf.global_variables_initializer())

        obs = env.reset()
        reward = 0  # do NOT use rewards to update policy
        success_num = 0

        for iteration in range(args.iteration):
            print("Iteration_Number",iteration)
            observations = []
            actions = []
            rewards = []
            v_preds = []
            run_policy_steps = 0
            while True:
                run_policy_steps += 1
                obs = np.stack([obs]).astype(dtype=np.float32)  # prepare to feed placeholder Policy.obs

                act, v_pred = Policy.act(obs=obs, stochastic=True)

                act = np.asscalar(act)
                v_pred = np.asscalar(v_pred)

                observations.append(obs)
                actions.append(act)
                rewards.append(reward)
                v_preds.append(v_pred)

                next_obs, reward, done, info = env.step(act)

                if done:
                    v_preds_next = v_preds[1:] + [0]  # next state of terminate state has 0 state value
                    obs = env.reset()
                    reward = -1
                    break
                else:
                    obs = next_obs

            writer.add_summary(tf.Summary(value=[tf.Summary.Value(tag='episode_length', simple_value=run_policy_steps)])
                               , iteration)
            writer.add_summary(tf.Summary(value=[tf.Summary.Value(tag='episode_reward', simple_value=sum(rewards))])
                               , iteration)

            if sum(rewards) >= 195:
                success_num += 1
                if success_num >= 100:
                    saver.save(sess, args.savedir + '/model.ckpt')
                    print('Clear!! Model saved.')
                    break
            else:
                success_num = 0

            # convert list to numpy array for feeding tf.placeholder
            observations = np.reshape(observations, newshape=[-1] + list(ob_space.shape))
            actions = np.array(actions).astype(dtype=np.int32)

            # train discriminator
            inp_d = [expert_observations,expert_actions,observations, actions]
            for i in range(2):
                sample_indices_d = np.random.randint(low=0, high=observations.shape[0],
                                                   size=32)  # indices are in [low, high)
                sampled_inp_d = [np.take(a=a, indices=sample_indices_d, axis=0) for a in inp_d]  # sample training data
                D.train(expert_s=sampled_inp_d[0],
                        expert_a=sampled_inp_d[1],
                        agent_s=sampled_inp_d[2],
                        agent_a=sampled_inp_d[3])
                l=D.get_wgan(expert_s=sampled_inp_d[0],
                        expert_a=sampled_inp_d[1],
                        agent_s=sampled_inp_d[2],
                        agent_a=sampled_inp_d[3])



                r_a=D.get_rewards(agent_s=sampled_inp_d[2],agent_a=sampled_inp_d[3])
                r_e=D.get_rewards_e(expert_s=sampled_inp_d[0],expert_a=sampled_inp_d[1])
                #print("Expert")
                #print(r_e)
                print("WGAN_gp_LOSS:",l)
                #print("___________________________________________________________________________________")
                #print("Agent")
                #print(r_a)


                print("One Iteration Don")
                print("_______________________________________________________________________")




            # output of this discriminator is reward
            d_rewards = D.get_rewards(agent_s=observations, agent_a=actions)            
            d_rewards = np.reshape(d_rewards, newshape=[-1]).astype(dtype=np.float32)



            gaes = PPO.get_gaes(rewards=d_rewards, v_preds=v_preds, v_preds_next=v_preds_next)
            gaes = np.array(gaes).astype(dtype=np.float32)
            # gaes = (gaes - gaes.mean()) / gaes.std()
            v_preds_next = np.array(v_preds_next).astype(dtype=np.float32)



            # train policy
            inp = [observations, actions, gaes, d_rewards, v_preds_next]
            print("Printing the rewards",d_rewards)
            PPO.assign_policy_parameters()
            for epoch in range(6):
                sample_indices = np.random.randint(low=0, high=observations.shape[0],
                                                   size=32)  # indices are in [low, high)
                sampled_inp = [np.take(a=a, indices=sample_indices, axis=0) for a in inp]  # sample training data
                PPO.train(obs=sampled_inp[0],
                          actions=sampled_inp[1],
                          gaes=sampled_inp[2],
                          rewards=sampled_inp[3],
                          v_preds_next=sampled_inp[4])

            summary = PPO.get_summary(obs=inp[0],
                                      actions=inp[1],
                                      gaes=inp[2],
                                      rewards=inp[3],
                                      v_preds_next=inp[4])

            writer.add_summary(summary, iteration)
        writer.close()


if __name__ == '__main__':
    args = argparser()
    main(args)
