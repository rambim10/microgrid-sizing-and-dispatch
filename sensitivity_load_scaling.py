from param import delta_t, C_pv_max, C_bss_max
from param import SOC_min_bss, SOC_max_bss, eff_bss
from param import C_ev, P_nom_ev, eff_ev, SOC_min_ev, SOC_max_ev, SOC_target_ev
from param import PI_gen, PI_imp, PI_exp
from param import P_max_hp, COP_hp, delta_T_max, C_hp
from param import PI_c_pv, PI_c_bss, PI_c_inv, PI_c_gen, inv_hor

from pyomo.environ import ConcreteModel, Param, Var, Objective, Constraint, NonNegativeReals, minimize, value
from datetime import datetime
import utils
import matplotlib.pyplot as plt

def create_model(res):
    # Create a concrete model
    model = ConcreteModel()

    model.periods = range(res.t_s)
    # model.connections = range(len(res.t_arr)) # A set is created with length equal to the number of EV connections

    # Access all parameters present in the res object.
    # These exists for each t in model.t:
    #  - model.P_load[t] = Load power at time t
    #  - model.P_pv_max[t] = Max available PV power at time t
    #  - model.EV_connected[t] = EV connected at time t
    #  - model.t_arr[t] = Bollean connexion of the EV
    #  - model.t_dep[t] = Boolean disconnexion of the EV
    #  - model.SOC_i_ev[t] = Initial SOC of the EV connected at time t (only non zero if t_arr[t] is true)
    model.P_load       = Param(model.periods, initialize=[res.P_load[t]       for t in model.periods], mutable=True)
    model.P_pv_max     = Param(model.periods, initialize=[res.P_pv_max[t]     for t in model.periods], mutable=True)
    model.EV_connected = Param(model.periods, initialize=[res.EV_connected[t]  for t in model.periods], mutable=True)
    model.t_arr        = Param(model.periods, initialize=[res.t_arr[t]        for t in model.periods], mutable=True)
    model.t_dep        = Param(model.periods, initialize=[res.t_dep[t]        for t in model.periods], mutable=True)
    model.SOC_i_ev     = Param(model.periods, initialize=[res.SOC_i_ev[t]     for t in model.periods], mutable=True)
    model.T_set        = Param(model.periods, initialize=[res.T_set[t]        for t in model.periods], mutable=True)
    model.P_loss       = Param(model.periods, initialize=[res.P_loss[t]       for t in model.periods], mutable=True)
    model.SOC_0_bss    = Param(initialize=0.5,           mutable=True)
    model.SOC_0_ev     = Param(initialize=0.5 * C_ev,    mutable=True)
    model.T_0_hp       = Param(initialize=res.T_set[0],  mutable=True)

    # Asset sizes
    model.P_nom_pv  = Var(within=NonNegativeReals)
    model.C_bss     = Var(within=[0, C_bss_max])
    model.C_pv      = Var(within=[0, C_pv_max])
    model.P_nom_bss = Var(within=NonNegativeReals)
    model.P_max_gen = Var(within=NonNegativeReals)
    model.P_nom_ev  = Param(initialize=P_nom_ev)
    model.C_ev      = Param(initialize=C_ev)
    model.P_nom_hp  = Param(initialize=P_max_hp)

    # Variables
    model.P_imp           = Var(model.periods, within=NonNegativeReals)
    model.P_exp           = Var(model.periods, within=NonNegativeReals)
    model.P_pv            = Var(model.periods, within=NonNegativeReals)
    model.P_gen           = Var(model.periods, within=NonNegativeReals)
    model.P_charge_bss    = Var(model.periods, within=NonNegativeReals)
    model.P_discharge_bss = Var(model.periods, within=NonNegativeReals)
    model.P_charge_ev     = Var(model.periods, within=NonNegativeReals)
    model.P_discharge_ev  = Var(model.periods, within=NonNegativeReals)
    model.P_hp_hot        = Var(model.periods, within=NonNegativeReals)
    model.P_hp_cold       = Var(model.periods, within=NonNegativeReals)
    model.T_hp            = Var(model.periods, within=NonNegativeReals)
    model.T_dev           = Var(model.periods, within=NonNegativeReals)

    
    # Energy storage variables for battery and EV
    model.SOC_bss = Var(model.periods, within=NonNegativeReals)
    model.SOC_ev  = Var(model.periods, within=NonNegativeReals)

    DISCOUNT_RATE = 0.06
    annual_OPEX = sum(delta_t * (PI_imp * model.P_imp[t] - PI_exp * model.P_exp[t] + PI_gen * model.P_gen[t]) for t in model.periods)
    CAPEX = (PI_c_pv * model.C_pv + PI_c_bss * model.C_bss + PI_c_inv * model.P_nom_pv + PI_c_inv * model.P_nom_bss + PI_c_gen * model.P_max_gen)

    model.objective = Objective(sense=minimize, expr = CAPEX + sum(annual_OPEX / ((1 + DISCOUNT_RATE) ** year) for year in range(1, inv_hor + 1)))
    
    # ─────────────────────────────────────────────────────────────────────────
    # Constraints
    # _________________________________________________________________________
    #PV
    model.power_balance_cstr = Constraint(model.periods, rule=lambda m, t: (m.P_pv[t] + m.P_gen[t] + m.P_discharge_bss[t] + m.P_discharge_ev[t]
                            + m.P_imp[t] == m.P_load[t] + m.P_charge_bss[t] + m.P_charge_ev[t] + m.P_hp_hot[t] + m.P_hp_cold[t] + m.P_exp[t]))
    model.pv_max_cstr = Constraint(model.periods, rule=lambda m, t: m.P_pv[t] <= m.P_pv_max[t] * m.C_pv)
    model.pv_nom_cstr_1 = Constraint(model.periods, rule=lambda m, t: m.P_pv[t] <= m.P_nom_pv)
    model.pv_nom_cstr_2 = Constraint(model.periods, rule=lambda m, t: m.P_nom_pv <= m.C_pv)
    
    #Genset
    model.gen_cstr = Constraint(model.periods, rule=lambda m, t: m.P_gen[t] <= m.P_max_gen)

    #BSS
    model.bss_nom_charge_cstr = Constraint(model.periods, rule=lambda m, t: m.P_charge_bss[t]    <= m.P_nom_bss)
    model.bss_nom_discharge_cstr = Constraint(model.periods, rule=lambda m, t: m.P_discharge_bss[t] <= m.P_nom_bss)
    model.bss_nom_cstr = Constraint(model.periods, rule=lambda m, t : m.P_nom_bss <= m.C_bss)
    model.bss_SOC_min_cstr = Constraint(model.periods, rule=lambda m, t: m.SOC_bss[t] >= SOC_min_bss * m.C_bss)
    model.bss_SOC_max_cstr = Constraint(model.periods, rule=lambda m, t: m.SOC_bss[t] <= SOC_max_bss * m.C_bss)
    model.bss_SOC_evolution_cstr = Constraint(model.periods, rule=lambda m, t: m.SOC_bss[t] == (m.SOC_0_bss if t == 0 else m.SOC_bss[t - 1])
                                + delta_t * (eff_bss * m.P_charge_bss[t] - m.P_discharge_bss[t] / eff_bss))

    #EV
    model.ev_charge_cstr = Constraint(model.periods, rule=lambda m, t: m.P_charge_ev[t] <= m.P_nom_ev * m.EV_connected[t])
    model.ev_discharge_cstr = Constraint(model.periods, rule=lambda m, t: m.P_discharge_ev[t] == 0)
    model.ev_SOC_evolution_cstr = Constraint(model.periods, rule=lambda m, t: m.SOC_ev[t] == 0 if value(m.EV_connected[t]) == 0 else m.SOC_ev[t] == (
                (m.SOC_i_ev[t] if t == 0 or value(m.t_arr[t]) == 1 else m.SOC_ev[t - 1]) + delta_t * eff_ev * m.P_charge_ev[t]))
    model.ev_SOC_departure_cstr = Constraint(model.periods, rule=lambda m, t: m.SOC_ev[t - 1] >= SOC_target_ev * m.C_ev if t > 0 and value(m.t_dep[t]) == 1
            else Constraint.Skip)
    model.ev_SOC_min_cstr = Constraint(model.periods, rule=lambda m, t: m.SOC_ev[t] >= SOC_min_ev * m.C_ev if value(m.EV_connected[t]) == 1 
            else Constraint.Skip)
    model.ev_SOC_max_cstr = Constraint(model.periods, rule=lambda m, t: m.SOC_ev[t] <= SOC_max_ev * m.C_ev if value(m.EV_connected[t]) == 1
            else Constraint.Skip)

    #Heat Pump
    model.p_max_cstr_1 = Constraint(model.periods, rule=lambda m, t: m.P_hp_hot[t]  <= P_max_hp)
    model.p_max_cstr_2 = Constraint(model.periods, rule=lambda m, t: m.P_hp_cold[t] <= P_max_hp)
    model.T_min_cstr = Constraint(model.periods, rule=lambda m, t: m.T_hp[t] >= m.T_set[t] - delta_T_max)
    model.T_max_cstr = Constraint(model.periods, rule=lambda m, t: m.T_hp[t] <= m.T_set[t] + delta_T_max)
    model.T_evolution_cstr = Constraint(model.periods, rule=lambda m, t: m.T_hp[t] == (m.T_0_hp if t == 0 else m.T_hp[t - 1]) 
                        + (delta_t * (COP_hp * (m.P_hp_hot[t] - m.P_hp_cold[t]) - m.P_loss[t])) / C_hp)

    return model


def run(model, results):
    model, results = utils.solve_model(model, results)
    if model and results:
        utils.check_res(results)
        utils.print_sizing_results(results)
        utils.print_res(results)
        utils.plot_res(results,n_days)
    return results


if __name__ == "__main__":
    start_time = datetime(2021, 1, 1, 0, 0, 0)
    n_days = 365

    load_factors = [0.8, 0.9, 1.0, 1.1, 1.2]

    investment_costs = []
    pv_sizes = []
    battery_sizes = []
    solved_factors = []

    for factor in load_factors:

        results = utils.Results(start_time, n_days, yearly_kwh=4000 * factor, yearly_km=15000 * factor) 
        results.P_loss = results.P_loss * factor

        model = create_model(results)
        model, results = utils.solve_model(model, results)

        if model and results:
            capex_total = (PI_c_pv * results.C_pv + PI_c_bss * results.C_bss + PI_c_inv * (results.P_nom_pv + results.P_nom_bss) + PI_c_gen * results.P_max_gen)
            annualised_capex = capex_total / inv_hor

            annual_opex = sum(delta_t * (PI_imp * results.P_imp[t] - PI_exp * results.P_exp[t] + PI_gen * results.P_gen[t]) for t in range(len(results.P_imp)))
            total_annual_cost = annualised_capex + annual_opex

            solved_factors.append(factor)
            investment_costs.append(total_annual_cost)
            pv_sizes.append(results.C_pv)
            battery_sizes.append(results.C_bss)

    plt.figure(figsize=(10, 5))
    plt.plot(solved_factors, investment_costs, marker='o')
    plt.xlabel("Load Factor")
    plt.ylabel("Total Annual Cost (€)")
    plt.title("Investment Cost vs Load Factor")
    plt.xticks(solved_factors)
    plt.grid(True)
    plt.show()

    plt.figure(figsize=(10, 5))
    plt.plot(solved_factors, pv_sizes, marker='o')
    plt.xlabel("Load Factor")
    plt.ylabel("PV Size (kWp)")
    plt.title("PV Size vs Load Factor")
    plt.xticks(solved_factors)
    plt.grid(True)
    plt.show()

    plt.figure(figsize=(10, 5))
    plt.plot(solved_factors, battery_sizes, marker='o')
    plt.xlabel("Load Factor")
    plt.ylabel("Battery Size (kWh)")
    plt.title("Battery Size vs Load Factor")
    plt.xticks(solved_factors)
    plt.grid(True)
    plt.show()
