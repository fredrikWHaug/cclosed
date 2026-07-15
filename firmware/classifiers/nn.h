/*
 * nn.h — tiny bare-metal neural-network inference primitives.
 *
 * Shared by every classifier firmware under firmware/classifiers/ so the
 * forward pass in each main.c reads like the PyTorch model, with no copy-paste
 * of the math. All ops are float32; BatchNorm is expected to be folded into the
 * preceding Conv/Linear weights at export time (see model/export_*_to_c.py),
 * so there is no bn op here.
 *
 * Every function is `static inline`: each firmware is a single translation
 * unit that includes this header, so this keeps them self-contained and emits
 * no "unused function" warnings for ops a given model doesn't use.
 *
 * Memory layout convention: a (channels, length) tensor is stored row-major,
 * i.e. index [c][t] == buf[c * length + t]. A flattened (C, L) tensor is thus
 * already contiguous and can be fed straight into nn_linear.
 */

#ifndef NN_H
#define NN_H

static inline float nn_relu(float x) { return x > 0.0f ? x : 0.0f; }

/*
 * conv1d, kernel_size=3, padding=1, stride=1  ->  output length == input length.
 * in:  (c_in,  len)
 * out: (c_out, len)
 * w:   (c_out, c_in, 3)   b: (c_out,)
 * apply_relu: 1 to ReLU the output (fused conv+relu), 0 for a bare conv
 *             (needed for the second conv inside a residual block).
 */
static inline void nn_conv1d(const float *in, float *out,
                             const float *w, const float *b,
                             int c_in, int c_out, int len, int apply_relu)
{
    for (int co = 0; co < c_out; co++) {
        for (int t = 0; t < len; t++) {
            float sum = b[co];
            for (int ci = 0; ci < c_in; ci++) {
                for (int k = 0; k < 3; k++) {
                    int tt = t + k - 1; /* padding=1 */
                    if (tt >= 0 && tt < len) {
                        sum += w[(co * c_in + ci) * 3 + k] * in[ci * len + tt];
                    }
                }
            }
            out[co * len + t] = apply_relu ? nn_relu(sum) : sum;
        }
    }
}

/*
 * max_pool1d, kernel_size=2, stride=2  ->  output length = len_in / 2.
 * in: (channels, len_in)   out: (channels, len_in / 2)
 */
static inline void nn_maxpool1d(const float *in, float *out,
                                int channels, int len_in)
{
    int len_out = len_in / 2;
    for (int c = 0; c < channels; c++) {
        for (int t = 0; t < len_out; t++) {
            float a = in[c * len_in + 2 * t];
            float b = in[c * len_in + 2 * t + 1];
            out[c * len_out + t] = a > b ? a : b;
        }
    }
}

/*
 * Residual add + ReLU, in place:  x = relu(x + residual)
 * Both x and residual are length n (a flattened (channels, len) block).
 * This is the join at the end of a ResBlock.
 */
static inline void nn_residual_add_relu(float *x, const float *residual, int n)
{
    for (int i = 0; i < n; i++) {
        x[i] = nn_relu(x[i] + residual[i]);
    }
}

/*
 * Fully-connected layer:  out = W * in + b, optional ReLU.
 * W: (out_dim, in_dim)   in: (in_dim,)   out: (out_dim,)
 */
static inline void nn_linear(const float *in, float *out,
                             const float *w, const float *b,
                             int in_dim, int out_dim, int apply_relu)
{
    for (int o = 0; o < out_dim; o++) {
        float sum = b[o];
        for (int i = 0; i < in_dim; i++) {
            sum += w[o * in_dim + i] * in[i];
        }
        out[o] = apply_relu ? nn_relu(sum) : sum;
    }
}

static inline int nn_argmax(const float *arr, int len)
{
    int best = 0;
    for (int i = 1; i < len; i++) {
        if (arr[i] > arr[best]) {
            best = i;
        }
    }
    return best;
}

#endif /* NN_H */
