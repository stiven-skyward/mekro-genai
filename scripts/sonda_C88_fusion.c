/* Sonda C88: ¿ahorra tiempo fundir en un bucle los pasos de una recurrencia,
 * frente a despacharlos como pasos separados que releen/reescriben el mismo
 * buffer de estado?
 *
 * NO es una reimplementación numéricamente exacta de gated-delta-rule —eso
 * exigiría leer el código de referencia y no es lo que decide esto—: es un
 * patrón de ACCESO A MEMORIA realista, con el tamaño de estado REAL de este
 * modelo (config.json real de qwen3.8-27b: linear_key_head_dim=128,
 * linear_num_value_heads=48 → estado por capa = 48*128*128 floats = 3 MB).
 *
 * "Sin fundir": 6 pasos, cada uno una pasada COMPLETA sobre el estado,
 * leyendo de un buffer y escribiendo a otro (simula operaciones separadas de
 * un grafo de cómputo, cada una con su propia entrada/salida en memoria).
 *
 * "Fundido": los mismos 6 pasos, por elemento, en un solo bucle — el valor
 * vive en un registro/variable local mientras se le aplican los 6 pasos,
 * y solo se lee el estado una vez y se escribe una vez.
 *
 * Misma cantidad de FLOPs en los dos casos: la diferencia que se mide es
 * SOLO tráfico de memoria, no trabajo aritmético de más ni de menos.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define VAL_HEADS 48
#define KEY_DIM 128
#define VAL_DIM 128
#define N_ELEM (VAL_HEADS * KEY_DIM * VAL_DIM)   /* 786432 floats = 3 MB */
#define N_CAPAS 48
#define N_TOKENS 200
#define N_PASOS 6

static double reloj_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

/* un paso "separado": lee TODO src, aplica una operación barata (multiplicar
 * y sumar una constante distinta por paso, para que el compilador no pueda
 * fundirlo él solo entre llamadas), escribe TODO a dst. */
static void paso_separado(const float *src, float *dst, float a, float b, long n) {
    for (long i = 0; i < n; i++) {
        dst[i] = src[i] * a + b;
    }
}

static double correr_sin_fundir(float *estado, float *tmp, long n) {
    double t0 = reloj_s();
    float coefs_a[N_PASOS] = {1.001f, 0.999f, 1.002f, 0.998f, 1.0005f, 0.9995f};
    float coefs_b[N_PASOS] = {0.01f, -0.01f, 0.02f, -0.02f, 0.005f, -0.005f};
    for (int capa = 0; capa < N_CAPAS; capa++) {
        for (int tok = 0; tok < N_TOKENS; tok++) {
            float *a = estado, *b = tmp;
            for (int p = 0; p < N_PASOS; p++) {
                paso_separado(a, b, coefs_a[p], coefs_b[p], n);
                float *aux = a; a = b; b = aux;
            }
            if (a != estado) memcpy(estado, a, n * sizeof(float));
        }
    }
    return reloj_s() - t0;
}

static double correr_fundido(float *estado, long n) {
    double t0 = reloj_s();
    float coefs_a[N_PASOS] = {1.001f, 0.999f, 1.002f, 0.998f, 1.0005f, 0.9995f};
    float coefs_b[N_PASOS] = {0.01f, -0.01f, 0.02f, -0.02f, 0.005f, -0.005f};
    for (int capa = 0; capa < N_CAPAS; capa++) {
        for (int tok = 0; tok < N_TOKENS; tok++) {
            for (long i = 0; i < n; i++) {
                float v = estado[i];
                for (int p = 0; p < N_PASOS; p++) {
                    v = v * coefs_a[p] + coefs_b[p];
                }
                estado[i] = v;
            }
        }
    }
    return reloj_s() - t0;
}

int main(void) {
    long n = N_ELEM;
    float *estado1 = malloc(n * sizeof(float));
    float *estado2 = malloc(n * sizeof(float));
    float *tmp = malloc(n * sizeof(float));
    if (!estado1 || !estado2 || !tmp) { fprintf(stderr, "sin memoria\n"); return 1; }
    for (long i = 0; i < n; i++) { estado1[i] = estado2[i] = 0.1f; }

    fprintf(stderr, "estado por capa: %.2f MB · %d capas x %d tokens x %d pasos\n",
           n * sizeof(float) / 1e6, N_CAPAS, N_TOKENS, N_PASOS);

    double t_sin = correr_sin_fundir(estado1, tmp, n);
    double t_con = correr_fundido(estado2, n);

    /* mismo resultado numérico en los dos caminos: si esto no coincide, el
     * "ahorro" sería trampa (menos trabajo, no menos tráfico) */
    double diff = 0;
    for (long i = 0; i < n; i++) diff += (estado1[i] - estado2[i]) * (estado1[i] - estado2[i]);
    fprintf(stderr, "diferencia numerica entre caminos (debe ser ~0): %.6e\n", diff);

    double ganancia = t_sin / t_con;
    printf("CIFRA t_sin_fundir_s %.4f\n", t_sin);
    printf("CIFRA t_fundido_s %.4f\n", t_con);
    printf("CIFRA ganancia %.4f\n", ganancia);

    free(estado1); free(estado2); free(tmp);
    return 0;
}
