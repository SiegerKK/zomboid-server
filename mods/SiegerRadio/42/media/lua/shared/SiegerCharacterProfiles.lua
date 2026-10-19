-- Fixed, reviewed roleplay presets. No executable payload is accepted over the network.
return {
 ["joel-arrival-v1"]={
  keep={ ["Base.Belt2"]=true,["Base.Shirt_Lumberjack"]=true,
   ["Base.Socks_Ankle"]=true,["Base.Shoes_TrainerTINT"]=true,
   ["Base.Trousers_Denim"]=true,["Base.IDcard"]=true,["Base.KeyRing"]=true },
  skills={Strength=7,Fitness=5,Aiming=5,Reloading=4,Blunt=6,SmallBlunt=5,
   SmallBlade=5,Sneak=5,Lightfoot=5,Nimble=4,Woodwork=4,Mechanics=3,Doctor=2},
  stats={HUNGER=.18,THIRST=.12,FATIGUE=.35,STRESS=.30},
  wounds={{part="ForeArm_L",time=8},{part="LowerLeg_R",time=6}},
  items={
   {"Base.Bag_NormalHikingBag",1,.65,"back"},
   {"Base.Revolver",1,.70},{"Base.Bullets357",12},
   {"Base.Shotgun",1,.65},{"Base.ShotgunShells",6},
   {"Base.HuntingRifle",1,.70},{"Base.308Bullets",6},
   {"Base.HuntingKnife",1,.60},{"Base.Torch",1,.70},
   {"Base.Battery",1},{"Base.Lighter",1},{"Base.DuctTape",1},
   {"Base.Bandage",2},{"Base.Disinfectant",1},{"Base.Pills",1},
   {"Base.WaterBottle",1},{"Base.BeefJerky",1},{"Base.TinnedBeans",1},
   {"Base.TinOpener",1},{"Base.Crackers",1},{"Base.Notebook",1},{"Base.Pencil",1}
  }
 }
}
