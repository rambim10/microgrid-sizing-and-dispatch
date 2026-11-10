from param import delta_t
from param import SOC_min_bss, SOC_max_bss, eff_bss
from param import C_ev, P_nom_ev, eff_ev, SOC_min_ev, SOC_max_ev, SOC_target_ev
from param import PI_gen, PI_imp, PI_exp
from param import P_max_hp, COP_hp, delta_T_max, C_hp
from pyomo.environ import ConcreteModel, Param, Var, Objective, Constraint, NonNegativeReals, minimize, value
from datetime import datetime
import utils

def create_model(res, C_pv, C_bss, P_nom_bss, P_nom_pv, P_max_gen):
    # Create a concrete model
    model = ConcreteModel()
    model.periods = range(res.t_s)

    # --- Parameters (Time Series) ---
    model.P_load = Param(model.periods, initialize=[res.P_load[t] for t in model.periods], mutable=True)
    model.P_pv_max = Param(model.periods, initialize=[res.P_pv_max[t] for t in  model.periods], mutable=True)
    model.EV_connected = Param(model.periods, initialize=[res.EV_connected[t] for t in  model.periods], mutable=True)
    model.t_arr = Param(model.periods, initialize=[res.t_arr[t] for t in model.periods], mutable=True)
    model.t_dep = Param(model.periods, initialize=[res.t_dep[t] for t in model.periods], mutable=True)
    model.SOC_i_ev = Param(model.periods, initialize=[res.SOC_i_ev[t] for t in model.periods], mutable=True)
    model.T_set = Param(model.periods, initialize=[res.T_set[t] for t in model.periods], mutable=True)
    model.P_loss = Param(model.periods, initialize=[res.P_loss[t] for t in model.periods], mutable=True)
    
    # --- Initial States ---
    model.SOC_0_bss = Param(initialize=0.5 * C_bss, mutable=True)
    model.SOC_0_ev = Param(initialize=0.5 * C_ev, mutable=True)
    model.T_0_hp = Param(initialize=res.T_set[0], mutable=True)

    # --- Operational planning asset sizes ---
    model.P_nom_pv = Param(initialize=P_nom_pv)                            
    model.C_bss = Param(initialize=C_bss)                                  
    model.C_pv = Param(initialize=C_pv)                                    
    model.P_nom_bss = Param(initialize=P_nom_bss)                          
    model.P_nom_ev = Param(initialize=P_nom_ev)                            
    model.C_ev = Param(initialize=C_ev)                                    
    model.P_max_gen = Param(initialize=P_max_gen)                          
    model.P_max_hp = Param(initialize=P_max_hp)

    # --- Variables (Power Flows in kW) ---
    model.P_imp = Var(model.periods, within=NonNegativeReals)              
    model.P_exp = Var(model.periods, within=NonNegativeReals)              
    model.P_pv = Var(model.periods, within=NonNegativeReals)               
    model.P_gen = Var(model.periods, within=NonNegativeReals)              
    model.P_charge_bss = Var(model.periods, within=NonNegativeReals)       
    model.P_discharge_bss = Var(model.periods, within=NonNegativeReals)    
    model.P_charge_ev = Var(model.periods, within=NonNegativeReals)        
    model.P_discharge_ev = Var(model.periods, within=NonNegativeReals)     
    model.P_hp_hot = Var(model.periods, within=NonNegativeReals) 
    model.P_hp_cold = Var(model.periods, within=NonNegativeReals) 
    
    # --- Variables (States) ---
    model.T_hp = Var(model.periods, within=NonNegativeReals)
    model.SOC_bss = Var(model.periods, within=NonNegativeReals)
    model.SOC_ev = Var(model.periods, within=NonNegativeReals)

 # --- State Limit Parameters ---
    model.SOC_bss_max = Param(initialize=SOC_max_bss * C_bss) 
    model.SOC_bss_min = Param(initialize=SOC_min_bss * C_bss)
    model.SOC_ev_min = Param(initialize=SOC_min_ev * C_ev)
    model.SOC_ev_max = Param(initialize=SOC_max_ev * C_ev)
    
# # --- Thermal Comfort ---
#     model.T_dev = Var(model.periods, within=NonNegativeReals)
#     model.W_comfort = Param(initialize=0.05) 

#     # Load Peak control for EV
#     model.EV_peak = Var(within=NonNegativeReals)
#     model.W_ev_smooth = Param(initialize=1.0)
    
#   # --- Grid Import Peak Control ---
#     model.P_peak = Var(within=NonNegativeReals)
#     model.PI_peak = Param(initialize=5.0)

    # ==============================================================================
    # 0. OBJECTIVE
    # ==============================================================================
    def objective_rule(m):
        financial_cost = sum(delta_t * (PI_gen * m.P_gen[t] + PI_imp * m.P_imp[t] - PI_exp * m.P_exp[t]) for t in m.periods)
        # comfort_penalty = sum(m.W_comfort * m.T_dev[t] for t in m.periods)
        # ev_smooth_cost = m.W_ev_smooth * m.EV_peak
        # peak_cost = m.PI_peak * m.P_peak
        
        return financial_cost #+ comfort_penalty + ev_smooth_cost + peak_cost
        
    model.objective = Objective(rule=objective_rule, sense=minimize)

    # POWER BALANCE
    def power_balance_rule(m, t):
        return (m.P_pv[t] + m.P_imp[t] + m.P_gen[t] + m.P_discharge_bss[t] + m.P_discharge_ev[t] == 
                m.P_exp[t] + m.P_load[t] + m.P_charge_bss[t] + m.P_charge_ev[t] + m.P_hp_hot[t] + m.P_hp_cold[t])
    model.power_balance_cstr = Constraint(model.periods, rule=power_balance_rule)

    # PV GENERATION
    model.P_pv_1_cstr = Constraint(model.periods, rule=lambda m, t: m.P_pv[t] <= m.P_pv_max[t] * m.C_pv)
    model.P_pv_2_cstr = Constraint(model.periods, rule=lambda m, t: m.P_pv[t] <= m.P_nom_pv)

    # DIESEL GENSET
    model.P_gen_max_cstr = Constraint(model.periods, rule=lambda m, t: m.P_gen[t] <= m.P_max_gen)

    # BATTERY STORAGE SYSTEM (BSS)
    model.P_charge_bss_cstr = Constraint(model.periods, rule=lambda m, t: m.P_charge_bss[t] <= m.P_nom_bss)
    model.P_discharge_bss_cstr = Constraint(model.periods, rule=lambda m, t: m.P_discharge_bss[t] <= m.P_nom_bss)
   
    def soc_bss_rule(m, t):
        prev_soc = m.SOC_0_bss if t == 0 else m.SOC_bss[t-1]
        return m.SOC_bss[t] == prev_soc + (m.P_charge_bss[t] * eff_bss - m.P_discharge_bss[t] / eff_bss) * delta_t
    model.SOC_bss_cstr = Constraint(model.periods, rule=soc_bss_rule)
    model.SOC_bss_min_cstr = Constraint(model.periods, rule=lambda m, t: m.SOC_bss[t] >= m.SOC_bss_min)
    model.SOC_bss_max_cstr = Constraint(model.periods, rule=lambda m, t: m.SOC_bss[t] <= m.SOC_bss_max)
    
    # EV
    model.P_charge_ev_cstr = Constraint(model.periods, rule=lambda m, t: m.P_charge_ev[t] <= m.P_nom_ev * m.EV_connected[t])
    model.P_discharge_ev_cstr = Constraint(model.periods, rule=lambda m, t: m.P_discharge_ev[t] <= m.P_nom_ev * m.EV_connected[t])

    def soc_ev_rule(m, t):
        if value(m.EV_connected[t]) == 0:
            return m.SOC_ev[t] == 0 
        else:
            prev_soc = m.SOC_i_ev[t] if value(m.t_arr[t]) == 1 else m.SOC_ev[t-1]
            return m.SOC_ev[t] == prev_soc + (m.P_charge_ev[t] * eff_ev - m.P_discharge_ev[t] / eff_ev) * delta_t
    model.SOC_ev_cstr = Constraint(model.periods, rule=soc_ev_rule)
    
    def soc_ev_bounds_min_rule(m, t):
        if value(m.EV_connected[t]) == 1:
            return m.SOC_ev[t] >= m.SOC_ev_min
        return Constraint.Skip
    model.SOC_ev_min_cstr = Constraint(model.periods, rule=soc_ev_bounds_min_rule)
    
    def soc_ev_bounds_max_rule(m, t):
        if value(m.EV_connected[t]) == 1:
            return m.SOC_ev[t] <= m.SOC_ev_max
        return Constraint.Skip
    model.SOC_ev_max_cstr = Constraint(model.periods, rule=soc_ev_bounds_max_rule)

    def soc_ev_target_rule(m, t):
        if value(m.t_dep[t]) == 1:
            if t > 0 and value(m.EV_connected[t]) == 0:
                return m.SOC_ev[t-1] >= SOC_target_ev * m.C_ev
            else:
                return m.SOC_ev[t] >= SOC_target_ev * m.C_ev
        return Constraint.Skip
    model.SOC_ev_target_cstr = Constraint(model.periods, rule=soc_ev_target_rule)

    # # EV Peak Charging Smoothing
    # def ev_peak_rule(m, t):
    #     return m.EV_peak >= m.P_charge_ev[t]
    # model.ev_peak_cstr = Constraint(model.periods, rule=ev_peak_rule)

    # # Grrid Import Peak Controlling
    # def peak_cstr_rule(m, t):
    #     return m.P_peak >= m.P_imp[t]
    # model.peak_cstr = Constraint(model.periods, rule=peak_cstr_rule)

    # HP
    model.P_hp_hot_cstr = Constraint(model.periods, rule=lambda m, t: m.P_hp_hot[t] <= m.P_max_hp)
    model.P_hp_cold_cstr = Constraint(model.periods, rule=lambda m, t: m.P_hp_cold[t] <= m.P_max_hp)

    def thermal_model_rule(m, t):
        T_prev = m.T_0_hp if t == 0 else m.T_hp[t-1]
        return m.T_hp[t] == T_prev + (delta_t / C_hp) * (COP_hp * (m.P_hp_hot[t] - m.P_hp_cold[t]) - m.P_loss[t])
    model.T_hp_cstr = Constraint(model.periods, rule=thermal_model_rule)

    model.T_set_min_cstr = Constraint(model.periods, rule=lambda m, t: m.T_hp[t] >= m.T_set[t] - delta_T_max)
    model.T_set_max_cstr = Constraint(model.periods, rule=lambda m, t: m.T_hp[t] <= m.T_set[t] + delta_T_max)

    # # --- NEW: Linear constraints to calculate Absolute Deviation |T_hp - T_set| ---
    # model.T_dev_cstr1 = Constraint(model.periods, rule=lambda m, t: m.T_dev[t] >= m.T_hp[t] - m.T_set[t])
    # model.T_dev_cstr2 = Constraint(model.periods, rule=lambda m, t: m.T_dev[t] >= m.T_set[t] - m.T_hp[t])

    return model

def run(model, results):
    model, results = utils.solve_model(model, results)
    if model and results:
        utils.check_res(results)
        utils.print_res(results)
        utils.plot_res(results,n_days)  
    return results

if __name__ == "__main__":
    start_time = datetime(2021, 1, 1, 0, 0, 0)
    n_days = 5

    # Asset sizes for operational planning base case
    C_pv = 10                            
    C_bss = 40                           
    P_nom_bss = 10                       
    P_nom_pv = 10                        
    P_max_gen = 10                       

    # Assuming standard consumption profile factors
    results = utils.Results(start_time, n_days, yearly_kwh=4000, yearly_km=15000)      
    model = create_model(results, C_pv, C_bss, P_nom_bss, P_nom_pv, P_max_gen)
    run(model, results)