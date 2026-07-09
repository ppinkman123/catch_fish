import torch
from transformers import GPT2LMHeadModel, GPT2Tokenizer


model = GPT2LMHeadModel.from_pretrained("/WORK/Test/gpt", torchscript=True).eval()

# tokenizer
tokenizer = GPT2Tokenizer.from_pretrained("/WORK/Test/gpt")
in_text = "Lionel Messi is a"
in_tokens = torch.tensor(tokenizer.encode(in_text))

# inference
token_eos = torch.tensor([198]) # line break symbol
out_token = None
kvcache = None
out_text = in_text
i = 0
with torch.no_grad():
    while out_token != token_eos:
        logits, kvcache = model(in_tokens, past_key_values=kvcache) # 增加了一个 past_key_values 的参数
        out_token = torch.argmax(logits[-1, :], dim=0, keepdim=True)
        in_tokens = out_token # 输出 token 直接作为下一轮的输入，不再拼接
        text = tokenizer.decode(in_tokens)
        print(f'step {i} input: {text}', flush=True)
        i += 1
        out_text += text

print(f' Input: {in_text}')
print(f'Output: {out_text}')


# 在推理时新增了 past_key_values 参数，该参数就会以追加方式保存每一轮的K V值。kvcache变量内容为((k,v), (k,v), ..., (k,v))，即有 
#  个 k,v 组成的一个元组，其中 k 和 v 的维度均为 [b, n_head, s, head_dims]。这里可以顺带计算出每轮推理对应的 cache 数据量为 
#  ，这里 
#  值等于当前轮次值。以GPT3-175B为例，假设以 float16 来保存 KV cache，senquence长度为100，batchsize=1，则 KV cache占用显存为 2×100×12288×96×2 Byte= 472MB。
# 推理输出的token直接作为下一轮的输入，不再拼接，因为上文信息已经在 kvcache 中。

# step 0 input: Lionel Messi is a player
# step 1 input: Lionel Messi is a player who
# step 2 input: Lionel Messi is a player who has
# step 3 input: Lionel Messi is a player who has been
# step 4 input: Lionel Messi is a player who has been a
# step 5 input: Lionel Messi is a player who has been a key
# step 6 input: Lionel Messi is a player who has been a key part
# step 7 input: Lionel Messi is a player who has been a key part of
# step 8 input: Lionel Messi is a player who has been a key part of the
# step 9 input: Lionel Messi is a player who has been a key part of the team
# step 10 input: Lionel Messi is a player who has been a key part of the team's
# step 11 input: Lionel Messi is a player who has been a key part of the team's success
# step 12 input: Lionel Messi is a player who has been a key part of the team's success.
# step 13 input: Lionel Messi is a player who has been a key part of the team's success.

#  Input: Lionel Messi is a
# Output: Lionel Messi is a player who has been a key part of the team's success.