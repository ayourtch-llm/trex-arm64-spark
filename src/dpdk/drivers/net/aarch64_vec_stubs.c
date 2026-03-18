/*
 * Stub implementations for x86 SSE vectorized functions on aarch64.
 * These functions are referenced by portable driver code but only
 * implemented in x86 SSE source files. On aarch64, scalar paths
 * are used instead; these stubs satisfy the linker.
 */

#include <stdint.h>
#include <stddef.h>

/* bnxt stubs */
uint16_t bnxt_recv_pkts_vec(void *rx_queue, void **rx_pkts, uint16_t nb_pkts)
{
    (void)rx_queue; (void)rx_pkts; (void)nb_pkts;
    return 0;
}

uint16_t bnxt_xmit_pkts_vec(void *tx_queue, void **tx_pkts, uint16_t nb_pkts)
{
    (void)tx_queue; (void)tx_pkts; (void)nb_pkts;
    return 0;
}

int bnxt_rxq_vec_setup(void *rxq)
{
    (void)rxq;
    return -1;
}

/* iavf stubs */
int iavf_rxq_vec_setup(void *rxq)
{
    (void)rxq;
    return -1;
}

int iavf_rx_vec_dev_check(void *dev)
{
    (void)dev;
    return -1; /* not supported */
}

uint16_t iavf_recv_pkts_vec(void *rx_queue, void **rx_pkts, uint16_t nb_pkts)
{
    (void)rx_queue; (void)rx_pkts; (void)nb_pkts;
    return 0;
}

uint16_t iavf_recv_pkts_vec_flex_rxd(void *rx_queue, void **rx_pkts, uint16_t nb_pkts)
{
    (void)rx_queue; (void)rx_pkts; (void)nb_pkts;
    return 0;
}

uint16_t iavf_recv_scattered_pkts_vec(void *rx_queue, void **rx_pkts, uint16_t nb_pkts)
{
    (void)rx_queue; (void)rx_pkts; (void)nb_pkts;
    return 0;
}

uint16_t iavf_recv_scattered_pkts_vec_flex_rxd(void *rx_queue, void **rx_pkts, uint16_t nb_pkts)
{
    (void)rx_queue; (void)rx_pkts; (void)nb_pkts;
    return 0;
}

uint16_t iavf_xmit_pkts_vec(void *tx_queue, void **tx_pkts, uint16_t nb_pkts)
{
    (void)tx_queue; (void)tx_pkts; (void)nb_pkts;
    return 0;
}

void iavf_rx_queue_release_mbufs_neon(void *rxq)
{
    (void)rxq;
}

/* i40e stubs */
uint16_t i40e_xmit_fixed_burst_vec(void *tx_queue, void **tx_pkts, uint16_t nb_pkts)
{
    (void)tx_queue; (void)tx_pkts; (void)nb_pkts;
    return 0;
}

uint16_t i40e_recv_pkts_vec(void *rx_queue, void **rx_pkts, uint16_t nb_pkts)
{
    (void)rx_queue; (void)rx_pkts; (void)nb_pkts;
    return 0;
}

uint16_t i40e_recv_scattered_pkts_vec(void *rx_queue, void **rx_pkts, uint16_t nb_pkts)
{
    (void)rx_queue; (void)rx_pkts; (void)nb_pkts;
    return 0;
}

int i40e_rxq_vec_setup(void *rxq)
{
    (void)rxq;
    return -1;
}

int i40e_txq_vec_setup(void *txq)
{
    (void)txq;
    return -1;
}

void i40e_rx_queue_release_mbufs_vec(void *rxq)
{
    (void)rxq;
}

int i40e_rx_vec_dev_check(void *dev)
{
    (void)dev;
    return -1;
}

int i40e_rx_vec_dev_conf_condition_check(void *dev)
{
    (void)dev;
    return -1;
}

/* ice stubs */
uint16_t ice_xmit_pkts_vec(void *tx_queue, void **tx_pkts, uint16_t nb_pkts)
{
    (void)tx_queue; (void)tx_pkts; (void)nb_pkts;
    return 0;
}

uint16_t ice_recv_pkts_vec(void *rx_queue, void **rx_pkts, uint16_t nb_pkts)
{
    (void)rx_queue; (void)rx_pkts; (void)nb_pkts;
    return 0;
}

uint16_t ice_recv_scattered_pkts_vec(void *rx_queue, void **rx_pkts, uint16_t nb_pkts)
{
    (void)rx_queue; (void)rx_pkts; (void)nb_pkts;
    return 0;
}

int ice_rxq_vec_setup(void *rxq)
{
    (void)rxq;
    return -1;
}

int ice_rx_vec_dev_check(void *dev)
{
    (void)dev;
    return -1;
}

/* EAL stubs */
/* rte_hypervisor_get: returns RTE_HYPERVISOR_UNKNOWN (0) on aarch64 */
enum rte_hypervisor { RTE_HYPERVISOR_UNKNOWN_STUB = 0 };
int rte_hypervisor_get(void)
{
    return 0; /* RTE_HYPERVISOR_UNKNOWN */
}
