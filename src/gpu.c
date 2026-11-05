#define VK_NO_PROTOTYPES
#include <windows.h>
#include <vulkan/vulkan.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned validation_errors;
static VKAPI_ATTR VkBool32 VKAPI_CALL debug_cb(VkDebugUtilsMessageSeverityFlagBitsEXT severity,
    VkDebugUtilsMessageTypeFlagsEXT type,const VkDebugUtilsMessengerCallbackDataEXT *data,void *user) {
    (void)type; (void)user;
    fprintf(stderr,"Vulkan validation: %s\n",data->pMessage);
    if(severity & VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT) ++validation_errors;
    return VK_FALSE;
}
#define GET(name) PFN_##name name=(PFN_##name)gpa(instance,#name); if(!name){fprintf(stderr,"Missing %s\n",#name); goto cleanup;}
#define CHECK(call) do{VkResult r=(call); if(r!=VK_SUCCESS){fprintf(stderr,"%s: VkResult=%d\n",#call,r);goto cleanup;}}while(0)
int oot_probe_gpu(int validation) {
    int result=1;
    HMODULE dll=LoadLibraryW(L"vulkan-1.dll");
    if(!dll){fputs("Vulkan loader unavailable\n",stderr);return 1;}
    PFN_vkGetInstanceProcAddr gpa=(PFN_vkGetInstanceProcAddr)GetProcAddress(dll,"vkGetInstanceProcAddr");
    VkInstance instance=VK_NULL_HANDLE;
    VkDevice device=VK_NULL_HANDLE;
    VkBuffer buffer=VK_NULL_HANDLE;
    VkDeviceMemory memory=VK_NULL_HANDLE;
    VkCommandPool pool=VK_NULL_HANDLE;
    VkFence fence=VK_NULL_HANDLE;
    VkDebugUtilsMessengerEXT messenger=VK_NULL_HANDLE;
    PFN_vkDestroyDevice destroy_device=NULL;
    PFN_vkDestroyBuffer destroy_buffer=NULL;
    PFN_vkFreeMemory free_memory=NULL;
    PFN_vkDestroyCommandPool destroy_pool=NULL;
    PFN_vkDestroyFence destroy_fence=NULL;
    validation_errors=0;
    if(!gpa) goto cleanup;
    GET(vkCreateInstance); GET(vkEnumerateInstanceLayerProperties);
    uint32_t count=0;
    CHECK(vkEnumerateInstanceLayerProperties(&count,NULL));
    VkLayerProperties *layers=calloc(count ? count:1,sizeof(*layers));
    if(!layers) goto cleanup;
    VkResult lr=vkEnumerateInstanceLayerProperties(&count,layers);
    int has_layer=0;
    for(uint32_t i=0;lr==VK_SUCCESS && i<count;++i) if(!strcmp(layers[i].layerName,"VK_LAYER_KHRONOS_validation")) has_layer=1;
    free(layers);
    if(validation && !has_layer){fputs("Validation requested but VK_LAYER_KHRONOS_validation is not installed\n",stderr);goto cleanup;}
    printf("validation=%s\n",validation ? "enabled":"disabled (use --validate to require layers)");
    const char *layer="VK_LAYER_KHRONOS_validation",*extension=VK_EXT_DEBUG_UTILS_EXTENSION_NAME;
    VkApplicationInfo app={.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.pApplicationName="OoT runtime GPU diagnostic",.apiVersion=VK_API_VERSION_1_3};
    VkInstanceCreateInfo ici={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&app,
        .enabledLayerCount=validation ? 1:0,.ppEnabledLayerNames=&layer,
        .enabledExtensionCount=validation ? 1:0,.ppEnabledExtensionNames=&extension};
    CHECK(vkCreateInstance(&ici,NULL,&instance));
    GET(vkEnumeratePhysicalDevices); GET(vkGetPhysicalDeviceProperties); GET(vkGetPhysicalDeviceQueueFamilyProperties);
    GET(vkGetPhysicalDeviceMemoryProperties); GET(vkCreateDevice);
    if(validation){
        GET(vkCreateDebugUtilsMessengerEXT);
        VkDebugUtilsMessengerCreateInfoEXT info={.sType=VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT,
            .messageSeverity=VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT|VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT,
            .messageType=VK_DEBUG_UTILS_MESSAGE_TYPE_GENERAL_BIT_EXT|VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT|VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT,
            .pfnUserCallback=debug_cb};
        CHECK(vkCreateDebugUtilsMessengerEXT(instance,&info,NULL,&messenger));
    }
    CHECK(vkEnumeratePhysicalDevices(instance,&count,NULL));
    if(!count){fputs("No Vulkan physical devices\n",stderr);goto cleanup;}
    VkPhysicalDevice *gpus=calloc(count,sizeof(*gpus));
    if(!gpus) goto cleanup;
    VkResult er=vkEnumeratePhysicalDevices(instance,&count,gpus);
    VkPhysicalDevice selected=VK_NULL_HANDLE;
    int best_score=-1;
    for(uint32_t i=0;er==VK_SUCCESS && i<count;++i){
        VkPhysicalDeviceProperties p; vkGetPhysicalDeviceProperties(gpus[i],&p);
        printf("GPU %u: %s vendor=0x%x api=%u.%u.%u driver=0x%x\n",i,p.deviceName,p.vendorID,VK_VERSION_MAJOR(p.apiVersion),VK_VERSION_MINOR(p.apiVersion),VK_VERSION_PATCH(p.apiVersion),p.driverVersion);
        int score=(p.deviceType==VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU ? 100:0)+(p.vendorID==0x1002 ? 10:0);
        if(p.apiVersion>=VK_API_VERSION_1_3 && score>best_score){selected=gpus[i];best_score=score;}
    }
    free(gpus);
    if(!selected){fputs("Vulkan 1.3 device required\n",stderr);goto cleanup;}
    VkPhysicalDeviceProperties chosen; vkGetPhysicalDeviceProperties(selected,&chosen);
    printf("Selected GPU: %s\n",chosen.deviceName);
    vkGetPhysicalDeviceQueueFamilyProperties(selected,&count,NULL);
    VkQueueFamilyProperties *queues=calloc(count ? count:1,sizeof(*queues));
    if(!queues) goto cleanup;
    vkGetPhysicalDeviceQueueFamilyProperties(selected,&count,queues);
    uint32_t family=UINT32_MAX;
    for(uint32_t i=0;i<count;++i) if(queues[i].queueCount && (queues[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)){family=i;break;}
    free(queues);
    if(family==UINT32_MAX) goto cleanup;
    float priority=1;
    VkDeviceQueueCreateInfo qci={.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,.queueFamilyIndex=family,.queueCount=1,.pQueuePriorities=&priority};
    VkDeviceCreateInfo dci={.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,.queueCreateInfoCount=1,.pQueueCreateInfos=&qci};
    CHECK(vkCreateDevice(selected,&dci,NULL,&device));
    destroy_device=(PFN_vkDestroyDevice)gpa(instance,"vkDestroyDevice");
    destroy_buffer=(PFN_vkDestroyBuffer)gpa(instance,"vkDestroyBuffer");
    free_memory=(PFN_vkFreeMemory)gpa(instance,"vkFreeMemory");
    destroy_pool=(PFN_vkDestroyCommandPool)gpa(instance,"vkDestroyCommandPool");
    destroy_fence=(PFN_vkDestroyFence)gpa(instance,"vkDestroyFence");
    GET(vkCreateBuffer); GET(vkGetBufferMemoryRequirements); GET(vkAllocateMemory); GET(vkBindBufferMemory);
    GET(vkCreateCommandPool); GET(vkAllocateCommandBuffers); GET(vkBeginCommandBuffer); GET(vkCmdFillBuffer);
    GET(vkCmdPipelineBarrier); GET(vkEndCommandBuffer); GET(vkGetDeviceQueue); GET(vkQueueSubmit);
    GET(vkCreateFence); GET(vkWaitForFences); GET(vkMapMemory); GET(vkUnmapMemory);
    VkBufferCreateInfo bci={.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,.size=4096,.usage=VK_BUFFER_USAGE_TRANSFER_DST_BIT,.sharingMode=VK_SHARING_MODE_EXCLUSIVE};
    CHECK(vkCreateBuffer(device,&bci,NULL,&buffer));
    VkMemoryRequirements req; vkGetBufferMemoryRequirements(device,buffer,&req);
    VkPhysicalDeviceMemoryProperties props; vkGetPhysicalDeviceMemoryProperties(selected,&props);
    uint32_t mt=UINT32_MAX;
    for(uint32_t i=0;i<props.memoryTypeCount;++i) if((req.memoryTypeBits&(1u<<i)) &&
        (props.memoryTypes[i].propertyFlags & (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT))==(VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)){mt=i;break;}
    if(mt==UINT32_MAX) goto cleanup;
    VkMemoryAllocateInfo mai={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,.allocationSize=req.size,.memoryTypeIndex=mt};
    CHECK(vkAllocateMemory(device,&mai,NULL,&memory)); CHECK(vkBindBufferMemory(device,buffer,memory,0));
    VkCommandPoolCreateInfo pci={.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,.queueFamilyIndex=family};
    CHECK(vkCreateCommandPool(device,&pci,NULL,&pool));
    VkCommandBufferAllocateInfo cai={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=pool,.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY,.commandBufferCount=1};
    VkCommandBuffer cmd; CHECK(vkAllocateCommandBuffers(device,&cai,&cmd));
    VkCommandBufferBeginInfo bi={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO}; CHECK(vkBeginCommandBuffer(cmd,&bi));
    vkCmdFillBuffer(cmd,buffer,0,4096,0x1234abcd);
    VkBufferMemoryBarrier barrier={.sType=VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER,.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,.dstAccessMask=VK_ACCESS_HOST_READ_BIT,
        .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.buffer=buffer,.offset=0,.size=4096};
    vkCmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,0,NULL,1,&barrier,0,NULL);
    CHECK(vkEndCommandBuffer(cmd));
    VkFenceCreateInfo fci={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO}; CHECK(vkCreateFence(device,&fci,NULL,&fence));
    VkQueue queue; vkGetDeviceQueue(device,family,0,&queue);
    VkSubmitInfo submit={.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,.commandBufferCount=1,.pCommandBuffers=&cmd};
    CHECK(vkQueueSubmit(queue,1,&submit,fence));
    CHECK(vkWaitForFences(device,1,&fence,VK_TRUE,10000000000ull));
    void *mapped=NULL; CHECK(vkMapMemory(device,memory,0,4096,0,&mapped));
    result=0;
    for(unsigned i=0;i<1024;++i) if(((uint32_t*)mapped)[i]!=0x1234abcd) result=1;
    vkUnmapMemory(device,memory);
cleanup:
    if(device){
        PFN_vkDeviceWaitIdle idle=(PFN_vkDeviceWaitIdle)gpa(instance,"vkDeviceWaitIdle");
        if(idle) idle(device);
        if(fence && destroy_fence) destroy_fence(device,fence,NULL);
        if(pool && destroy_pool) destroy_pool(device,pool,NULL);
        if(buffer && destroy_buffer) destroy_buffer(device,buffer,NULL);
        if(memory && free_memory) free_memory(device,memory,NULL);
        if(destroy_device) destroy_device(device,NULL);
    }
    if(messenger){PFN_vkDestroyDebugUtilsMessengerEXT fn=(PFN_vkDestroyDebugUtilsMessengerEXT)gpa(instance,"vkDestroyDebugUtilsMessengerEXT"); if(fn) fn(instance,messenger,NULL);}
    if(instance){PFN_vkDestroyInstance fn=(PFN_vkDestroyInstance)gpa(instance,"vkDestroyInstance"); if(fn) fn(instance,NULL);}
    FreeLibrary(dll);
    if(validation_errors) result=1;
    if(!result) puts("PASS Vulkan 1.3: device creation, command submission, buffer fill, barrier, fence and 4096-byte readback. This is NOT game rendering.");
    return result;
}
