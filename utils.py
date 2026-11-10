from pyomo.environ import SolverFactory, SolverStatus
from datetime import timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from param import *
from param import PI_c_pv, PI_c_bss, PI_c_inv, PI_c_gen, inv_hor

def check_res(res):
    eps = 1e-3  # 1 W or 0.1% error tolerance
    violations = 0
    for t in range(len(res.t)):
        generation = res.P_pv[t] + res.P_gen[t] + res.P_imp[t]
        consumption = res.P_load[t] + res.P_exp[t] + res.P_hp_hot[t] + res.P_hp_cold[t] + res.P_bss[t] + res.P_ev[t]
        if abs(generation - consumption) > eps:
            violations += 1       
    if violations == 0:
        print("Constraint Check: All physical power balance constraints strictly respected.")
    else:
        print(f"Constraint Check: WARNING! {violations} power balance violations detected.")
    return

def print_res(res):
    print("\n" + "="*50)
    print("           OPERATIONAL PLANNING RESULTS           ")
    print("="*50)
    real_opex = np.sum(delta_t * (0.60 * res.P_gen + 0.40 * res.P_imp - 0.03 * res.P_exp))
    print(f"Total Objective (OPEX): € {real_opex:,.2f}")
    
    print("-" * 50)
    
    # Base Demands
    total_load = np.sum(res.P_load) * delta_t
    total_hp_hot = np.sum(res.P_hp_hot) * delta_t
    total_hp_cold = np.sum(res.P_hp_cold) * delta_t
    
    # EV Net Charging 
    total_ev_charged = np.sum(res.P_ev[res.P_ev > 0]) * delta_t
    
    # PV 
    total_pv_gen = np.sum(res.P_pv_max * res.C_pv) * delta_t
    total_exp = np.sum(res.P_exp) * delta_t
    pv_utilized = np.sum(res.P_pv) * delta_t - total_exp
    
    # BSS 
    bss_charged = np.sum(res.P_bss[res.P_bss > 0]) * delta_t
    bss_discharged = np.sum(-res.P_bss[res.P_bss < 0]) * delta_t
    
    # External Sources
    total_imp = np.sum(res.P_imp) * delta_t
    total_gen = np.sum(res.P_gen) * delta_t
    
    # --- PRINT OUTPUTS ---
    print(f"Total Base Load Demand:      {total_load:,.2f} kWh")
    print(f"Total HP Heating Energy:     {total_hp_hot:,.2f} kWh")
    print(f"Total HP Cooling Energy:     {total_hp_cold:,.2f} kWh")
    print(f"Total EV Energy Charged:     {total_ev_charged:,.2f} kWh")
    print("-" * 50)
    print(f"Total PV Energy Generated:   {total_pv_gen:,.2f} kWh")
    print(f"PV Energy Utilized Locally:  {pv_utilized:,.2f} kWh")
    print(f"Excess PV Injected to Grid:  {total_exp:,.2f} kWh")
    print(f"Excess PV to Battery:        {bss_charged:,.2f} kWh")
    print("-" * 50)
    print(f"Battery Energy Charged:      {bss_charged:,.2f} kWh")
    print(f"Battery Energy Discharged:   {bss_discharged:,.2f} kWh")
    print("-" * 50)
    print(f"Total Grid Import:           {total_imp:,.2f} kWh")
    print(f"Total Grid Export:           {total_exp:,.2f} kWh")
    print(f"Total Genset Produced:       {total_gen:,.2f} kWh")
    print("="*50 + "\n")
    return

def print_sizing_results(res):
    print("\n" + "="*50)
    print("                 SIZING RESULTS                   ")
    print("="*50)
    print(f"PV System Size:              {res.C_pv:,.2f} kWp")
    print(f"Battery Capacity:            {res.C_bss:,.2f} kWh")
    print(f"Battery Inverter Nominal:    {res.P_nom_bss:,.2f} kW")
    print(f"PV Inverter Nominal:         {res.P_nom_pv:,.2f} kW")
    print(f"Genset Maximum Power:        {res.P_max_gen:,.2f} kW")
    print("-" * 50)
    # Cost breakdown (only meaningful after a sizing solve)
    try:
        capex_total  = (PI_c_pv  * res.C_pv
                      + PI_c_bss * res.C_bss
                      + PI_c_inv * (res.P_nom_pv + res.P_nom_bss)
                      + PI_c_gen * res.P_max_gen)
        capex_annual = capex_total / inv_hor
        opex_annual  = np.sum(delta_t * (PI_imp * res.P_imp
                                        - PI_exp * res.P_exp
                                        + PI_gen * res.P_gen))
        print(f"Total CAPEX:                 € {capex_total:,.0f}")
        print(f"Annualised CAPEX /{inv_hor}yr:    € {capex_annual:,.0f}/yr")
        print(f"Annual OPEX:                 € {opex_annual:,.0f}/yr")
        print(f"Total Annual Cost:           € {capex_annual + opex_annual:,.0f}/yr")
    except Exception:
        pass
    print("="*50 + "\n")
    return

def plot_res(res, days_to_plot):
    steps = int(days_to_plot * 24 / delta_t)
    time_axis = res.datetime[:steps]
    
    fig, axs = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    
    # Power Flows
    axs[0].plot(time_axis, res.P_load[:steps], label='Fixed Load', color='black', linestyle='--')
    axs[0].plot(time_axis, res.P_pv[:steps], label='PV Generation', color='orange', alpha=0.8)
    axs[0].plot(time_axis, res.P_imp[:steps], label='Grid Import', color='red', alpha=0.6)
    axs[0].plot(time_axis, -res.P_exp[:steps], label='Grid Export', color='green', alpha=0.6)
    axs[0].plot(time_axis, res.P_bss[:steps], label='BSS Net Power (Charge>0)', color='blue', alpha=0.5)
    axs[0].plot(time_axis, res.P_gen[:steps], label='Diesel Genset', color='purple', alpha=0.6)
    
    # Heat Pump power (heating + cooling)
    P_hp_total = res.P_hp_hot[:steps] + res.P_hp_cold[:steps]
    axs[0].plot(time_axis, P_hp_total, label='Heat Pump', color='magenta', alpha=0.6)
    
    # EV power
    axs[0].plot(time_axis, res.P_ev[:steps], label='EV Net Power (Charge>0)', color='teal', alpha=0.8)
    
    axs[0].set_ylabel('Power (kW)')
    axs[0].set_title(f'Microgrid Power Flows')
    axs[0].legend(loc='upper right', bbox_to_anchor=(1.15, 1))
    axs[0].grid(True, alpha=0.3)

    # State of Charge
    axs[1].plot(time_axis, res.SOC_bss[:steps], label='Battery SOC', color='blue')
    axs[1].plot(time_axis, res.SOC_ev[:steps], label='EV SOC', color='teal')
    axs[1].set_ylabel('Energy (kWh)')
    axs[1].set_title('Storage States of Charge')
    axs[1].legend(loc='upper right', bbox_to_anchor=(1.15, 1))
    axs[1].grid(True, alpha=0.3)

    # Comfort bounds
    axs[2].plot(time_axis, res.T_hp[:steps], label='House Temp', color='red')
    axs[2].plot(time_axis, res.T_set[:steps], label='Set Point', color='black', linestyle='--')
    axs[2].fill_between(time_axis, res.T_set[:steps] - delta_T_max, res.T_set[:steps] + delta_T_max, color='gray', alpha=0.2, label='Comfort Range')
    axs[2].set_ylabel('Temperature (°C)')
    axs[2].set_title('Thermal Comfort (Heat Pump Management)')
    axs[2].legend(loc='upper right', bbox_to_anchor=(1.15, 1))
    axs[2].grid(True, alpha=0.3)

    plt.xlabel('Date/Time')
    plt.tight_layout()
    plt.show()

def solve_model(m, res):
    solver = SolverFactory('gurobi')
    output = solver.solve(m)

    status = output.solver.status
    if status == SolverStatus.ok:
        print("Simulation completed successfully.")
        res = save_results(res, m)
        res.save_sizing_results(m)
        return m, res
    elif status == SolverStatus.warning:
        print("Solver finished with a warning.")
    elif status == SolverStatus.error:
        print("Solver encountered an error and did not converge.")
    elif status == SolverStatus.aborted:
        print("Solver was aborted before completing.")
    else:
        print("Solver status unknown.")
    return None, None

def update_model(model, res, SOC_0_bss, SOC_0_ev, T_0_hp):
    for t in res.t:
        model.P_load[t] = res.P_load[t]
        model.P_pv_max[t] = res.P_pv_max[t]
        model.EV_connected[t] = res.EV_connected[t]
        model.t_arr[t] = res.t_arr[t]
        model.t_dep[t] = res.t_dep[t]
        model.SOC_i_ev[t] = res.SOC_i_ev[t]
        model.T_set[t] = res.T_set[t]
        model.P_loss[t] = res.P_loss[t]
    model.SOC_0_bss = SOC_0_bss
    model.SOC_0_ev = SOC_0_ev
    model.T_0_hp = T_0_hp
    return model

class Results:
    def __init__(self, start_time, n_days, yearly_kwh, yearly_km):
        self.start_time = start_time 
        self.t_s = int(n_days * 24 / delta_t)
        self.n_days = n_days
        self.yearly_kwh = yearly_kwh
        self.yearly_km = yearly_km
        self.t = np.arange(0, self.t_s)

        self.P_pv = np.zeros(self.t_s)
        self.P_bss = np.zeros(self.t_s)
        self.P_ev = np.zeros(self.t_s)
        self.P_gen = np.zeros(self.t_s)
        self.P_imp = np.zeros(self.t_s)
        self.P_exp = np.zeros(self.t_s)
        self.SOC_ev = np.zeros(self.t_s)
        self.SOC_bss = np.zeros(self.t_s)

        # Load data from CSV
        self.df = pd.read_csv('microgrid_timeseries.csv', delimiter=';', index_col="DateTime", parse_dates=True, date_format='%Y-%m-%d %H:%M:%S')
        self.P_load = np.array([self.df.loc[self.start_time + timedelta(hours=t*delta_t)]["Load"].clip(min=0) * self.yearly_kwh for t in self.t])
        self.P_pv_max = np.array([self.df.loc[self.start_time + timedelta(hours=t*delta_t)]["PV"].clip(min=0) for t in self.t])
        self.EV_connected_raw = np.array([self.df.loc[self.start_time + timedelta(hours=t*delta_t)]["EV"] for t in self.t])
        self.P_loss = np.array([self.df.loc[self.start_time + timedelta(hours=t*delta_t)]["P_loss"] for t in self.t])
        self.T_set = np.array([self.df.loc[self.start_time + timedelta(hours=t*delta_t)]["T_set"] for t in self.t])
        self.datetime = [self.start_time + timedelta(hours=t*delta_t) for t in self.t]

        # Extract EV logic array
        self.SOC_i_ev = np.array([SOC_target_ev*C_ev - (self.EV_connected_raw[t]*self.yearly_km) / (5e6) if self.EV_connected_raw[t] > 0 and (t == 0 or self.EV_connected_raw[t-1] == 0) else 0 for t in range(self.t_s)])
        self.t_arr = np.array([1 if self.EV_connected_raw[t] > 0 and (t == 0 or self.EV_connected_raw[t-1] == 0) else 0 for t in range(self.t_s)])
        self.t_dep = np.array([1 if self.EV_connected_raw[t] == 0 and (t > 0 and self.EV_connected_raw[t-1] > 0) else 0 for t in range(self.t_s)])
        
        # Enforce target boundary condition for edge case
        if self.EV_connected_raw[-1] > 0: self.t_dep[-1] = 1
        
        self.EV_connected = np.array([1 if self.EV_connected_raw[t] > 0 else 0 for t in range(self.t_s)])

    def save_sizing_results(self, m):
        try:
            self.C_bss = m.C_bss.value
            self.P_nom_bss = m.P_nom_bss.value
            self.C_pv = m.C_pv.value
            self.P_nom_pv = m.P_nom_pv.value
            self.C_ev = m.C_ev.value
            self.P_nom_ev = m.P_nom_ev.value
            self.P_max_gen = m.P_max_gen.value
        except ValueError:
            pass

def save_results(res, m):
    res.P_imp = np.array([m.P_imp[t].value for t in m.periods])
    res.P_exp = np.array([m.P_exp[t].value for t in m.periods])
    res.P_pv = np.array([m.P_pv[t].value for t in m.periods])
    res.P_bss = np.array([m.P_charge_bss[t].value - m.P_discharge_bss[t].value for t in m.periods])
    res.P_ev = np.array([m.P_charge_ev[t].value - m.P_discharge_ev[t].value for t in m.periods])
    res.P_gen = np.array([m.P_gen[t].value for t in m.periods])
    res.P_hp_hot = np.array([m.P_hp_hot[t].value for t in m.periods])
    res.P_hp_cold = np.array([m.P_hp_cold[t].value for t in m.periods])
    res.T_hp = np.array([m.T_hp[t].value for t in m.periods])
    res.SOC_ev = np.array([m.SOC_ev[t].value for t in m.periods])
    res.SOC_bss = np.array([m.SOC_bss[t].value for t in m.periods])
    res.objective = m.objective()
    return res